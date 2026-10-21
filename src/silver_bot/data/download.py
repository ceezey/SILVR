"""Download Binance Futures candle history into monthly CSV files for backtests.
With ``--funding`` it downloads funding-rate history into one CSV file instead.

Only public market data is requested: ``main`` always builds the adapter for the
production public API with no credentials and never reads ``.env`` keys or
``TRADING_MODE``. Each file is written to ``<name>.part`` and then renamed, so a
crash never leaves a half-written file that looks complete.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from silver_bot.config import ConfigError, load_config
from silver_bot.data.csv_loader import timeframe_interval
from silver_bot.data.funding import FundingDataError, FundingSchedule, write_funding_csv
from silver_bot.exchange.base import ExchangeAdapter
from silver_bot.exchange.binance_futures import BinanceFuturesAdapter
from silver_bot.models import Candle

FETCH_LIMIT = 1500  # Binance USD-M klines maximum per request.
CSV_HEADER = ["open_time", "open", "high", "low", "close", "volume", "close_time"]
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MS = timedelta(milliseconds=1)


@dataclass(frozen=True)
class DownloadSummary:
    candles: int
    files: list[Path]
    skipped: list[Path]
    gaps: int


def month_file_name(symbol: str, timeframe: str, year: int, month: int) -> str:
    return f"{symbol}-{timeframe}-{year:04d}-{month:02d}.csv"


def _to_ms(value: datetime) -> int:
    return (value - _EPOCH) // _MS


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _month_start(year: int, month: int) -> datetime:
    return datetime(year, month, 1, tzinfo=UTC)


def _edge_open_times(path: Path) -> tuple[int, int] | None:
    """Return the first and last row open_time (ms) of a candle CSV, or None if unreadable."""

    first: int | None = None
    last: int | None = None
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.reader(handle):
                if not row or row[0].strip().lower() == "open_time":
                    continue
                value = int(row[0])
                if first is None:
                    first = value
                last = value
    except (OSError, ValueError):
        return None
    return None if first is None or last is None else (first, last)


def _is_complete(path: Path, *, first_ms: int, last_ms: int, month_end: datetime, end: datetime, now: datetime) -> bool:
    if month_end > end or month_end > now or not path.is_file():
        return False
    return _edge_open_times(path) == (first_ms, last_ms)


def _count_missing(candles: list[Candle], interval: timedelta, window_start: datetime, window_end: datetime) -> int:
    """Count intervals missing from the expected window: every interval from window_start that
    closes by window_end, including holes at the window edges and a wholly empty window."""

    expected = max(0, (window_end - window_start) // interval)
    limit = window_start + interval * expected
    present = {c.open_time for c in candles if window_start <= c.open_time < limit}
    return expected - len(present)


def _write_atomic(path: Path, candles: list[Candle], interval_ms: int) -> None:
    part = path.with_name(path.name + ".part")
    try:
        with part.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(CSV_HEADER)
            for candle in candles:
                open_ms = _to_ms(candle.open_time)
                writer.writerow(
                    [open_ms, candle.open, candle.high, candle.low, candle.close, candle.volume, open_ms + interval_ms - 1]
                )
        os.replace(part, path)
    finally:
        part.unlink(missing_ok=True)


async def download(
    *,
    symbol: str,
    timeframe: str,
    start: date,
    end: datetime,
    out_dir: Path,
    adapter: ExchangeAdapter,
) -> DownloadSummary:
    """Download ``[start, end)`` as one CSV file per UTC month into ``out_dir``."""

    interval = timeframe_interval(timeframe)
    interval_ms = interval // _MS
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    start_dt = datetime(start.year, start.month, start.day, tzinfo=UTC)
    if start_dt >= end:
        raise ValueError("start must be before end")
    now = datetime.now(UTC)
    out_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    gaps = 0
    files: list[Path] = []
    skipped: list[Path] = []
    year, month = start.year, start.month
    while _month_start(year, month) < end:
        month_begin = _month_start(year, month)
        month_end = _month_start(*_next_month(year, month))
        path = out_dir / month_file_name(symbol, timeframe, year, month)
        first_ms = _to_ms(month_begin)
        last_ms = _to_ms(month_end) - interval_ms
        if _is_complete(path, first_ms=first_ms, last_ms=last_ms, month_end=month_end, end=end, now=now):
            print(f"{path.name}: complete, skipped")
            skipped.append(path)
        else:
            window_start = max(month_begin, start_dt)
            candles = list(
                await adapter.fetch_ohlcv_history(
                    symbol=symbol,
                    timeframe=timeframe,
                    start=window_start,
                    end=min(month_end, end),
                    limit=FETCH_LIMIT,
                )
            )
            month_gaps = _count_missing(candles, interval, window_start, min(month_end, end, now))
            gaps += month_gaps
            if not candles:
                print(f"{path.name}: no candles returned, no file written, {month_gaps} gaps")
            else:
                _write_atomic(path, candles, interval_ms)
                print(f"{path.name}: {len(candles)} candles, {month_gaps} gaps")
                files.append(path)
                total += len(candles)
        year, month = _next_month(year, month)
    return DownloadSummary(candles=total, files=files, skipped=skipped, gaps=gaps)


async def download_funding(
    *, symbol: str, start: date, end: datetime, out_dir: Path, adapter: BinanceFuturesAdapter
) -> Path | None:
    """Download funding rates for ``[start, end)`` into ``<out_dir>/<symbol>-funding.csv``."""

    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    start_dt = datetime(start.year, start.month, start.day, tzinfo=UTC)
    if start_dt >= end:
        raise ValueError("start must be before end")
    rates = await adapter.fetch_funding_rates(symbol=symbol, start=start_dt, end=end)
    if not rates:
        print(f"{symbol}-funding.csv: no funding rates returned, no file written")
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{symbol}-funding.csv"
    write_funding_csv(path, rates)
    try:
        FundingSchedule(rates).check_coverage(start_dt, end)
        note = "no gaps"
    except FundingDataError as exc:
        note = f"WARNING {exc} (a backtest over this range will refuse to run)"
    print(f"{path.name}: {len(rates)} funding rates, {note}")
    return path


def _parse_day(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=UTC)


def _config_default(name: str, fallback: str) -> str:
    try:
        return str(getattr(load_config(), name))
    except ConfigError as exc:
        print(f"note: config could not be loaded ({exc}); using default {name} {fallback}", file=sys.stderr)
        return fallback


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download Binance Futures candle history to monthly CSV files.")
    parser.add_argument("--start", help="first day, YYYY-MM-DD (UTC)")
    parser.add_argument("--end", help="end day, YYYY-MM-DD (UTC, exclusive); default now")
    parser.add_argument("--symbol")
    parser.add_argument("--timeframe")
    parser.add_argument("--out", help="output directory; default data/candles, or data/funding with --funding")
    parser.add_argument("--funding", action="store_true", help="download funding-rate history instead of candles")
    try:
        args = parser.parse_args(argv)
        if not args.start:
            raise ValueError("--start YYYY-MM-DD is required")
        start = _parse_day(args.start)
        end = _parse_day(args.end) if args.end else datetime.now(UTC)
        symbol = args.symbol or _config_default("symbol", "BTCUSDT")
        if args.funding:
            path = asyncio.run(
                download_funding(
                    symbol=symbol,
                    start=start.date(),
                    end=end,
                    out_dir=Path(args.out or "data/funding"),
                    adapter=BinanceFuturesAdapter(),
                )
            )
            print(f"done: {'1 funding file written' if path else 'no funding file written'}")
            return 0
        timeframe = args.timeframe or _config_default("timeframe", "1m")
        # Production public API, no credentials, whatever .env says.
        summary = asyncio.run(
            download(
                symbol=symbol,
                timeframe=timeframe,
                start=start.date(),
                end=end,
                out_dir=Path(args.out or "data/candles"),
                adapter=BinanceFuturesAdapter(),
            )
        )
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) and exc.code == 0 else 1
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        f"done: {summary.candles} candles written, {len(summary.files)} files "
        f"({len(summary.skipped)} skipped), {summary.gaps} gaps (reported, not filled)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
