"""Binance USD-M funding-rate history: CSV format, loader and a gap-checked schedule.

Funding is charged at each funding timestamp while a position is open (spec 3.6, TD-16). The
schedule fails closed: a gap in the history raises ``FundingDataError`` and the engine never
assumes a zero rate.
"""

from __future__ import annotations

import csv
import math
import os
from bisect import bisect_left, bisect_right
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

CSV_HEADER = ["time_ms", "rate"]
# Funding is paid every 8 hours; one minute of slack covers the exchange's millisecond offsets.
MAX_FUNDING_GAP = timedelta(hours=8, minutes=1)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MS = timedelta(milliseconds=1)


class FundingDataError(ValueError):
    """Funding data is unreadable, missing or has a gap."""


@dataclass(frozen=True, slots=True)
class FundingRate:
    time: datetime
    rate: float


def _sorted_unique(rates: Iterable[FundingRate]) -> list[FundingRate]:
    by_time: dict[datetime, FundingRate] = {}
    for rate in rates:
        by_time.setdefault(rate.time, rate)
    return [by_time[time] for time in sorted(by_time)]


def write_funding_csv(path: Path, rates: Iterable[FundingRate]) -> None:
    """Write ``time_ms,rate`` rows to ``<name>.part`` and rename, so a crash leaves no partial file."""

    path = Path(path)
    part = path.with_name(path.name + ".part")
    try:
        with part.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(CSV_HEADER)
            for item in rates:
                writer.writerow([(item.time - _EPOCH) // _MS, repr(item.rate)])
        os.replace(part, path)
    finally:
        part.unlink(missing_ok=True)


def load_funding_csv(path: Path) -> list[FundingRate]:
    """Read a funding CSV, sorted by time with duplicate timestamps dropped."""

    path = Path(path)
    rates: list[FundingRate] = []
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            if next(reader, None) != CSV_HEADER:
                raise FundingDataError(f"{path}: expected header {','.join(CSV_HEADER)}")
            for line, row in enumerate(reader, start=2):
                if not row:
                    continue
                try:
                    rate = float(row[1])
                    if not math.isfinite(rate):
                        raise ValueError("non-finite rate")
                    rates.append(FundingRate(_EPOCH + int(row[0]) * _MS, rate))
                except (ValueError, IndexError):
                    raise FundingDataError(f"{path}: bad funding row on line {line}: {row!r}") from None
    except OSError as exc:
        raise FundingDataError(f"{path}: cannot read funding data ({exc})") from exc
    return _sorted_unique(rates)


class FundingSchedule:
    """Funding rates sorted by time, queried by window."""

    def __init__(self, rates: Iterable[FundingRate]) -> None:
        self._rates = _sorted_unique(rates)
        self._times = [item.time for item in self._rates]

    def due(self, start_exclusive: datetime, end_inclusive: datetime) -> list[FundingRate]:
        """Rates with ``start_exclusive < time <= end_inclusive``."""

        low = bisect_right(self._times, start_exclusive)
        high = bisect_right(self._times, end_inclusive)
        return self._rates[low:high]

    def check_coverage(self, start: datetime, end: datetime) -> None:
        """Raise ``FundingDataError`` unless ``[start, end]`` is covered with no gap over 8h + 1 min.

        ``start`` and ``end`` are boundary points. The chain is the last rate at or before ``start``,
        the rates inside the window and the first rate at or after ``end``; ``start`` / ``end`` stand
        in for a missing neighbour. Every consecutive gap in the chain must be within the limit, which
        also absorbs the exchange's millisecond offsets.
        """

        if not self._rates:
            raise FundingDataError("no funding rates loaded")
        before = bisect_right(self._times, start) - 1
        after = bisect_left(self._times, end)
        chain = self._times[max(before, 0) : after + 1]
        if before < 0:
            chain.insert(0, start)
        if after >= len(self._times):
            chain.append(end)
        for earlier, later in zip(chain, chain[1:]):
            if later - earlier > MAX_FUNDING_GAP:
                raise FundingDataError(
                    f"funding gap between {earlier.isoformat()} and {later.isoformat()} "
                    f"(checking {start.isoformat()} to {end.isoformat()})"
                )
