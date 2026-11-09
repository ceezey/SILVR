"""Application entrypoint: run the configured mode.

Backtest mode runs trend_ensemble on local Binance kline CSV files through the trend runner.
Paper and demo modes have no strategy yet and exit with a usage error before any network call
or database connection. Live trading cannot be configured at all.
"""

from __future__ import annotations

import argparse

from silvr.backtest import trend_runner
from silvr.config import AppConfig, ConfigError, TradingMode, load_config
from silvr.monitoring import StructuredAuditLogger
from silvr.strategy.trend import params
from silvr.utils.logging import get_logger


logger = get_logger(__name__)

EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser."""

    parser = argparse.ArgumentParser(
        prog="silvr",
        description="Run the configured SILVR mode. Live trading is not available.",
    )
    parser.add_argument("--candles", default="data/candles", metavar="DIR", help="Root of the 1m kline CSV files.")
    parser.add_argument("--funding", default="data/funding", metavar="DIR", help="Root of the funding-rate CSV files.")
    parser.add_argument("--output-dir", default="reports", help="Directory for reports (default: reports).")
    parser.add_argument("--segments", choices=("training", "all"), default="training")
    parser.add_argument("--strategy", choices=(params.STRATEGY_NAME,), default=params.STRATEGY_NAME)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Load configuration, run the configured mode and return an exit code."""

    args = build_parser().parse_args(argv)
    try:
        config = load_config()
    except ConfigError as exc:
        logger.error("configuration rejected: %s", exc)
        return EXIT_USAGE

    audit = StructuredAuditLogger("logs/audit.jsonl")
    audit.log(
        "bot_started",
        "SILVR started",
        context={
            "mode": config.mode.value,
            "paper_trading": config.paper_trading,
            "ml_filter_enabled": config.ml_filter_enabled,
            "telegram_enabled": config.telegram_enabled,
        },
    )
    exit_code = 1  # reported if dispatch raises; matches Python's uncaught-exception exit
    try:
        exit_code = _dispatch(config, args)
    finally:
        audit.log("bot_stopped", "SILVR stopped", context={"mode": config.mode.value, "exit_code": exit_code})
    return exit_code


def _dispatch(config: AppConfig, args: argparse.Namespace) -> int:
    if config.mode != TradingMode.BACKTEST:
        logger.error("no strategy available for paper or demo mode yet: trend_ensemble runs in backtest only")
        return EXIT_USAGE
    return trend_runner.main(
        [
            "--candles-root", args.candles,
            "--funding-root", args.funding,
            "--output-dir", args.output_dir,
            "--segments", args.segments,
        ]
    )
