"""Daily bars, Donchian breakout, channel-midpoint stop and volatility for trend_ensemble."""

import math
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from silvr.data.resample import Resampler
from silvr.models import Candle
from silvr.strategy.trend.params import VOL_WINDOW


@dataclass(frozen=True)
class DailyBar:
    """One complete UTC day of one symbol."""

    symbol: str
    day: date
    open: float
    high: float
    low: float
    close: float


def daily_bars(candles: Iterable[Candle]) -> list[DailyBar]:
    """Complete daily bars from 1m candles. The trailing open day is never emitted (no flush)."""

    resampler = Resampler("1d")
    bars: list[DailyBar] = []
    for candle in candles:
        for htf in resampler.push(candle):
            c = htf.candle
            if not htf.complete:
                raise ValueError(f"incomplete daily bar for {c.symbol} on {c.open_time.date().isoformat()}")
            bars.append(DailyBar(c.symbol, c.open_time.date(), c.open, c.high, c.low, c.close))
    return bars


def is_breakout(closes: Sequence[float], n: int) -> bool:
    """True when the last close is strictly above the previous n closes."""

    return len(closes) >= n + 1 and closes[-1] > max(closes[-1 - n : -1])


def channel_mid(closes: Sequence[float], n: int) -> float:
    """Midpoint of the highest and lowest close of the last n days."""

    if len(closes) < n:
        raise ValueError(f"need {n} closes, got {len(closes)}")
    window = closes[-n:]
    return (max(window) + min(window)) / 2


def raise_stop(current: float, candidate: float) -> float:
    """A stop only ever moves up."""

    return max(current, candidate)


def simple_returns(closes: Sequence[float]) -> list[float]:
    """Close-to-close simple returns."""

    return [b / a - 1 for a, b in zip(closes, closes[1:])]


def annualized_vol(closes: Sequence[float], window: int = VOL_WINDOW) -> float | None:
    """Sample stdev of the last `window` daily returns times sqrt(365); None during warm-up."""

    if len(closes) < window + 1:
        return None
    return statistics.stdev(simple_returns(closes[-window - 1 :])) * math.sqrt(365)
