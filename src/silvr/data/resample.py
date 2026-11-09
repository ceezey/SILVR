"""Causal 1m to 15m/4h/1d candle builder.

A higher-timeframe candle is emitted only once a later 1m candle proves its period is over,
so nothing built here can be used before its close time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from silvr.data.csv_loader import timeframe_interval
from silvr.models import Candle

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MINUTE = timedelta(minutes=1)
_TIMEFRAMES = ("15m", "4h", "1d")


@dataclass(frozen=True, slots=True)
class HtfCandle:
    """A higher-timeframe candle; complete is False when 1m minutes were missing from its period."""

    candle: Candle
    complete: bool


class Resampler:
    """Feed 1m candles oldest first; get back each higher-timeframe period as it closes."""

    def __init__(self, timeframe: str) -> None:
        if timeframe not in _TIMEFRAMES:
            raise ValueError(f"Unsupported resample timeframe: {timeframe!r}")
        self._timeframe = timeframe
        self._period = timeframe_interval(timeframe)
        self._bars: list[Candle] = []  # 1m candles of the open period
        self._start: datetime | None = None
        self._last_open: datetime | None = None

    def push(self, candle: Candle) -> list[HtfCandle]:
        """Emit the period that ended at or before candle.open_time (if any), then add candle."""

        if self._last_open is not None and candle.open_time <= self._last_open:
            raise ValueError(f"1m candles must arrive in strictly increasing order: {candle.open_time.isoformat()}")
        self._last_open = candle.open_time
        start = _EPOCH + (candle.open_time - _EPOCH) // self._period * self._period
        emitted = self.flush() if self._start is not None and start != self._start else []
        self._start = start
        self._bars.append(candle)
        return emitted

    def flush(self) -> list[HtfCandle]:
        """Emit the open period, if any. For end of data only; the strategy never calls it mid-run."""

        if self._start is None:
            return []
        bars, start = self._bars, self._start
        self._bars, self._start = [], None
        merged = Candle(
            symbol=bars[0].symbol,
            timeframe=self._timeframe,
            open_time=start,
            open=bars[0].open,
            high=max(bar.high for bar in bars),
            low=min(bar.low for bar in bars),
            close=bars[-1].close,
            volume=sum(bar.volume for bar in bars),
            close_time=start + self._period - timedelta(milliseconds=1),
        )
        return [HtfCandle(candle=merged, complete=len(bars) == self._period // _MINUTE)]
