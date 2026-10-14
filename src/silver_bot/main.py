"""Application entrypoint: run the configured mode.

Backtest mode runs on local Binance kline CSV files. Paper and demo modes read
closed candles from the Binance Futures public klines endpoint (the testnet in
demo mode) and fill trades in the local paper executor; no order is sent to
any exchange. Live trading cannot be configured at all.
"""

from __future__ import annotations

import argparse
import asyncio
import signal
from pathlib import Path

from silver_bot.backtest.runner import run_backtest
from silver_bot.config import AppConfig, ConfigError, TradingMode, load_config
from silver_bot.data.csv_loader import CandleDataError, load_binance_kline_csv
from silver_bot.exchange import BinanceFuturesAdapter
from silver_bot.execution.runtime import run_paper_session
from silver_bot.monitoring import StructuredAuditLogger
from silver_bot.storage import SQLiteStorage
from silver_bot.utils.logging import get_logger


logger = get_logger(__name__)

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2


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
        help="Directory for reports (default: reports).",
    )
    parser.add_argument(
        "--max-candles",
        type=int,
        default=None,
        metavar="N",
        help="Paper and demo only: stop after N new closed candles (for smoke runs).",
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
    exit_code = 1  # reported if dispatch raises; matches Python's uncaught-exception exit
    try:
        exit_code = _dispatch(config, args, audit, storage)
    finally:
        audit.log("bot_stopped", "Silver bot stopped", context={"mode": config.mode.value, "exit_code": exit_code})
    return exit_code


def _dispatch(
    config: AppConfig,
    args: argparse.Namespace,
    audit: StructuredAuditLogger,
    storage: SQLiteStorage,
) -> int:
    if config.mode == TradingMode.BACKTEST:
        if args.max_candles is not None:
            logger.error("--max-candles only applies to paper and demo modes")
            return EXIT_USAGE
        return _run_backtest(config, args)
    if args.candles:
        logger.error("--candles only applies to backtest mode")
        return EXIT_USAGE
    if args.max_candles is not None and args.max_candles < 1:
        logger.error("--max-candles must be at least 1")
        return EXIT_USAGE
    return _run_market_mode(config, args, audit, storage)


def _run_market_mode(
    config: AppConfig,
    args: argparse.Namespace,
    audit: StructuredAuditLogger,
    storage: SQLiteStorage,
) -> int:
    """Run paper or demo mode until stopped; SIGTERM stops it like Ctrl+C."""

    previous_handler = signal.signal(signal.SIGTERM, _interrupt)
    try:
        asyncio.run(
            run_paper_session(
                config,
                adapter=BinanceFuturesAdapter.from_config(config),
                storage=storage,
                audit=audit,
                output_dir=Path(args.output_dir),
                max_candles=args.max_candles,
            )
        )
    except KeyboardInterrupt:
        logger.info("%s session stopped by signal", config.mode.value)
        return EXIT_OK
    except ConnectionError as exc:
        logger.error("market data unavailable: %s", exc)
        audit.log("market_data_unavailable", str(exc), context={"mode": config.mode.value}, level="ERROR")
        return EXIT_FAILURE
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
    return EXIT_OK


def _interrupt(signum: int, frame: object) -> None:
    raise KeyboardInterrupt


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
