"""Higher-timeframe bias detection."""

from __future__ import annotations

from collections.abc import Sequence

from silver_bot.models import Candle
from silver_bot.strategy.models import BiasDirection


def determine_higher_timeframe_bias(
    candles: Sequence[Candle],
    *,
    lookback: int = 5,
) -> BiasDirection:
    """Determine a simple bullish, bearish, or neutral HTF bias."""

    if lookback < 2:
        raise ValueError("lookback must be at least 2")
    if len(candles) < lookback:
        return BiasDirection.NEUTRAL

    sample = candles[-lookback:]
    first = sample[0]
    last = sample[-1]
    highs_up = last.high > first.high
    lows_up = last.low > first.low
    highs_down = last.high < first.high
    lows_down = last.low < first.low

    if last.close > first.close and highs_up and lows_up:
        return BiasDirection.BULLISH
    if last.close < first.close and highs_down and lows_down:
        return BiasDirection.BEARISH
    return BiasDirection.NEUTRAL
