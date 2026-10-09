"""Application entrypoint: run the configured mode.

Backtest mode runs on local Binance kline CSV files. Paper and demo modes are
not available until real market data exists (G-13) and exit 78 so that
supervisors stop restarting. Live trading cannot be configured at all.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from silver_bot.backtest.runner import run_backtest
from silver_bot.config import AppConfig, ConfigError, TradingMode, load_config
from silver_bot.data.csv_loader import CandleDataError, load_binance_kline_csv
from silver_bot.monitoring import StructuredAuditLogger
from silver_bot.storage import SQLiteStorage
from silver_bot.utils.logging import get_logger


logger = get_logger(__name__)

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_MODE_UNAVAILABLE = 78
MODE_UNAVAILABLE_MESSAGE = "mode not available yet: needs market data (G-13)"


def build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser."""

    parser = argparse.ArgumentParser(
        prog="silver-bot",
        description="Run the configured Silver Bot mode. Live trading is not available.",
    )
    parser.add_argument(
        "--candles",
        action="append",
        default=[],
        metavar="PATH",
        help="Binance kline CSV file or directory of them (backtest mode only; repeatable).",
    )
    parser.add_argument(
        "--output-dir",
        default="reports",
        help="Directory for backtest reports (default: reports).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Load configuration, run the configured mode and return an exit code."""

    args = build_parser().parse_args(argv)
    try:
        config = load_config()
    except ConfigError as exc:
        logger.error("configuration rejected: %s", exc)
        return EXIT_USAGE

    storage = SQLiteStorage(config.database_path)
    storage.initialize()
    audit = StructuredAuditLogger("logs/audit.jsonl")
    audit.log(
        "bot_started",
        "Silver bot started",
        context={
            "mode": config.mode.value,
            "paper_trading": config.paper_trading,
            "database_path": str(config.database_path),
            "ml_filter_enabled": config.ml_filter_enabled,
            "telegram_enabled": config.telegram_enabled,
        },
    )
    exit_code = _dispatch(config, args, audit)
    audit.log("bot_stopped", "Silver bot stopped", context={"mode": config.mode.value, "exit_code": exit_code})
    return exit_code


def _dispatch(config: AppConfig, args: argparse.Namespace, audit: StructuredAuditLogger) -> int:
    if config.mode == TradingMode.BACKTEST:
        return _run_backtest(config, args)
    if args.candles:
        logger.error("--candles only applies to backtest mode")
        return EXIT_USAGE
    logger.error("%s %s", config.mode.value, MODE_UNAVAILABLE_MESSAGE)
    audit.log("mode_unavailable", MODE_UNAVAILABLE_MESSAGE, context={"mode": config.mode.value}, level="WARNING")
    return EXIT_MODE_UNAVAILABLE


def _run_backtest(config: AppConfig, args: argparse.Namespace) -> int:
    if not args.candles:
        logger.error("backtest mode needs --candles")
        return EXIT_USAGE
    try:
        loaded = load_binance_kline_csv(args.candles, symbol=config.symbol, timeframe=config.timeframe)
    except CandleDataError as exc:
        logger.error("candle data rejected: %s", exc)
        return EXIT_USAGE
    summary = run_backtest(
        config,
        loaded.candles,
        Path(args.output_dir),
        inputs={"files": [str(path) for path in loaded.files], "gaps": loaded.gaps},
    )
    for name, path in sorted(summary.report_paths.items()):
        logger.info("wrote %s: %s", name, path)
    logger.info("backtest complete: %d candles, %d gaps", summary.candles, loaded.gaps)
    return EXIT_OK
