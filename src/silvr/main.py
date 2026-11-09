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
from urllib.parse import urlsplit

import psycopg

from silvr.backtest.runner import STRATEGIES, TOP_DOWN_STRATEGIES, run_backtest
from silvr.config import AppConfig, ConfigError, TradingMode, load_config
from silvr.data.csv_loader import CandleDataError, load_binance_kline_csv
from silvr.data.funding import FundingDataError, FundingSchedule, load_funding_csv
from silvr.exchange import BinanceFuturesAdapter
from silvr.execution.runtime import run_paper_session
from silvr.monitoring import StructuredAuditLogger
from silvr.storage import PostgresStorage
from silvr.utils.logging import get_logger


logger = get_logger(__name__)

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser."""

    parser = argparse.ArgumentParser(
        prog="silvr",
        description="Run the configured SILVR mode. Live trading is not available.",
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
    parser.add_argument(
        "--strategy",
        choices=STRATEGIES,
        default="silver_bullet",
        help="Backtest strategy (default: silver_bullet).",
    )
    parser.add_argument(
        "--funding",
        metavar="PATH",
        help="Funding-rate CSV; required with the top-down strategies, ignored by silver_bullet.",
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
        exit_code = _dispatch(config, args, audit)
    finally:
        audit.log("bot_stopped", "SILVR stopped", context={"mode": config.mode.value, "exit_code": exit_code})
    return exit_code


def _dispatch(
    config: AppConfig,
    args: argparse.Namespace,
    audit: StructuredAuditLogger,
) -> int:
    if config.mode == TradingMode.BACKTEST:
        if args.max_candles is not None:
            logger.error("--max-candles only applies to paper and demo modes")
            return EXIT_USAGE
        return _run_backtest(config, args)
    if args.candles:
        logger.error("--candles only applies to backtest mode")
        return EXIT_USAGE
    if args.funding or args.strategy != "silver_bullet":
        logger.error("--strategy and --funding only apply to backtest mode")
        return EXIT_USAGE
    if args.max_candles is not None and args.max_candles < 1:
        logger.error("--max-candles must be at least 1")
        return EXIT_USAGE
    return _run_market_mode(config, args, audit)


def _run_market_mode(
    config: AppConfig,
    args: argparse.Namespace,
    audit: StructuredAuditLogger,
) -> int:
    """Run paper or demo mode until stopped; SIGTERM stops it like Ctrl+C."""

    try:
        adapter = BinanceFuturesAdapter.from_config(config)
    except ValueError as exc:
        logger.error("configuration rejected: %s", exc)
        return EXIT_USAGE
    if config.database_url is None:
        logger.error("configuration rejected: DATABASE_URL is required in %s mode", config.mode.value)
        return EXIT_USAGE
    storage = PostgresStorage(config.database_url)
    try:
        storage.initialize()
    except psycopg.Error as exc:
        # libpq can echo parts of a malformed URL, so the password never reaches a log.
        password = urlsplit(config.database_url).password
        message = str(exc).replace(password, "***") if password else str(exc)
        logger.error("database unavailable: %s", message)
        audit.log("database_unavailable", message, context={"mode": config.mode.value}, level="ERROR")
        return EXIT_FAILURE
    previous_handler = signal.signal(signal.SIGTERM, _interrupt)
    try:
        asyncio.run(
            run_paper_session(
                config,
                adapter=adapter,
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
    top_down = args.strategy in TOP_DOWN_STRATEGIES
    if top_down and not args.funding:
        logger.error("--strategy %s needs --funding PATH", args.strategy)
        return EXIT_USAGE
    try:
        loaded = load_binance_kline_csv(args.candles, symbol=config.symbol, timeframe=config.timeframe)
    except CandleDataError as exc:
        logger.error("candle data rejected: %s", exc)
        return EXIT_USAGE
    inputs = {"files": [str(path) for path in loaded.files], "gaps": loaded.gaps}
    funding = None
    try:
        if top_down:
            funding = FundingSchedule(load_funding_csv(Path(args.funding)))
            inputs["funding_file"] = args.funding
        summary = run_backtest(
            config, loaded.candles, Path(args.output_dir), inputs=inputs, strategy=args.strategy, funding=funding
        )
    except FundingDataError as exc:
        logger.error("funding data rejected: %s", exc)
        return EXIT_USAGE
    for name, path in sorted(summary.report_paths.items()):
        logger.info("wrote %s: %s", name, path)
    logger.info("backtest complete: %d candles, %d gaps", summary.candles, loaded.gaps)
    return EXIT_OK
