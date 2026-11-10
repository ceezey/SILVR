"""Load Binance public kline CSV files (data.binance.vision) into candles.

Offline only: the owner downloads the files; nothing here touches the network.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from silvr.models import Candle

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MICROSECOND_THRESHOLD = 10**15
_UNIT_MINUTES = {"m": 1, "h": 60, "d": 1440, "w": 10080}


class CandleDataError(ValueError):
    """Raised when candle input files are missing or malformed."""


@dataclass(frozen=True, slots=True)
class CandleLoadResult:
    """Validated candles plus where they came from."""

    candles: list[Candle]
    files: list[Path]
    gaps: int


def timeframe_interval(timeframe: str) -> timedelta:
    """Return the candle interval for a timeframe such as 1m, 4h or 1d."""

    value = timeframe.strip().lower()
    if len(value) < 2 or not value[:-1].isdigit() or value[-1] not in _UNIT_MINUTES or int(value[:-1]) <= 0:
        raise CandleDataError(f"Unsupported timeframe: {timeframe!r}")
    return timedelta(minutes=int(value[:-1]) * _UNIT_MINUTES[value[-1]])


def load_binance_kline_csv(
    paths: Sequence[str | Path],
    *,
    symbol: str,
    timeframe: str,
) -> CandleLoadResult:
    """Load, validate, de-duplicate and sort Binance kline CSV rows."""

    interval = timeframe_interval(timeframe)
    files = _expand(paths)
    by_open_time: dict[datetime, Candle] = {}
    for file in files:
        for line_number, row in _rows(file):
            candle = parse_kline_row(row, where=f"{file}:{line_number}", symbol=symbol, timeframe=timeframe)
            duration = candle.close_time - candle.open_time
            if duration != interval:
                raise CandleDataError(
                    f"{file}:{line_number}: candle duration {duration} does not match TIMEFRAME={timeframe}"
                )
            existing = by_open_time.get(candle.open_time)
            if existing is None:
                by_open_time[candle.open_time] = candle
            elif existing != candle:
                raise CandleDataError(
                    f"{file}:{line_number}: conflicting duplicate candle at {candle.open_time.isoformat()}"
                )
    if not by_open_time:
        raise CandleDataError("No candle rows found in: " + ", ".join(str(file) for file in files))

    candles = [by_open_time[key] for key in sorted(by_open_time)]
    gaps = 0
    for previous, current in zip(candles, candles[1:]):
        step = current.open_time - previous.open_time
        if step % interval != timedelta(0):
            raise CandleDataError(
                f"Candle spacing {step} before {current.open_time.isoformat()} "
                f"is not a multiple of TIMEFRAME={timeframe}"
            )
        if step > interval:
            gaps += 1
    return CandleLoadResult(candles=candles, files=files, gaps=gaps)


def _expand(paths: Sequence[str | Path]) -> list[Path]:
    if not paths:
        raise CandleDataError("No candle paths given")
    files: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            found = sorted(item for item in path.iterdir() if item.is_file() and item.suffix.lower() == ".csv")
            if not found:
                raise CandleDataError(f"No .csv files in {path}")
            files.extend(found)
        elif path.is_file():
            files.append(path)
        else:
            raise CandleDataError(f"Candle path not found: {path}")
    return files


def _rows(file: Path) -> Iterator[tuple[int, list[str]]]:
    with file.open(newline="", encoding="utf-8-sig") as handle:
        for line_number, row in enumerate(csv.reader(handle), start=1):
            if not row or all(not cell.strip() for cell in row):
                continue
            if line_number == 1 and row[0].strip().lower() == "open_time":
                continue
            yield line_number, row


def parse_kline_row(row: list[str], *, where: str, symbol: str, timeframe: str) -> Candle:
    """Validate one Binance kline row (CSV file or REST response) as a candle."""

    if len(row) < 7:
        raise CandleDataError(f"{where}: expected at least 7 columns, got {len(row)}")
    try:
        open_raw = int(row[0])
        close_raw = int(row[6])
    except ValueError as exc:
        raise CandleDataError(f"{where}: timestamps must be integers") from exc
    try:
        open_, high, low, close, volume = (float(cell) for cell in row[1:6])
    except ValueError as exc:
        raise CandleDataError(f"{where}: OHLCV values must be numbers") from exc
    if not all(math.isfinite(price) and price > 0 for price in (open_, high, low, close)):
        raise CandleDataError(f"{where}: prices must be finite and positive")
    if not math.isfinite(volume) or volume < 0:
        raise CandleDataError(f"{where}: volume must be finite and non-negative")
    try:
        return Candle(
            symbol=symbol,
            timeframe=timeframe,
            open_time=_to_utc(open_raw),
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=volume,
            close_time=_to_utc(close_raw + 1),
        )
    except (ValueError, OverflowError) as exc:
        raise CandleDataError(f"{where}: {exc}") from exc


def _to_utc(raw: int) -> datetime:
    """Convert a Binance ms (or, from 10**15 up, µs) timestamp to UTC."""

    if raw < 0:
        raise ValueError("timestamp must be non-negative")
    micros = raw if raw >= _MICROSECOND_THRESHOLD else raw * 1000
    return _EPOCH + timedelta(microseconds=micros)
