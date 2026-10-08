"""Displacement candle detection."""

from __future__ import annotations

from collections.abc import Sequence

from silver_bot.models import Candle
from silver_bot.strategy.models import DisplacementEvent, FairValueGapDirection


def average_true_range(candles: Sequence[Candle], *, period: int = 5) -> float:
    """Calculate simple ATR from available candles."""

    if period < 1:
        raise ValueError("period must be positive")
    if len(candles) < 2:
        return 0.0

    ranges: list[float] = []
    start = max(1, len(candles) - period)
    for index in range(start, len(candles)):
        current = candles[index]
        previous = candles[index - 1]
        true_range = max(
            current.high - current.low,
            abs(current.high - previous.close),
            abs(current.low - previous.close),
        )
        ranges.append(true_range)
    return sum(ranges) / len(ranges) if ranges else 0.0


def detect_displacement(
    candles: Sequence[Candle],
    *,
    direction: FairValueGapDirection,
    atr_period: int = 5,
    body_multiplier: float = 1.2,
    range_multiplier: float = 1.0,
    candle_index: int | None = None,
) -> DisplacementEvent | None:
    """Detect a strong directional candle using body, range, and ATR filters."""

    if body_multiplier <= 0:
        raise ValueError("body_multiplier must be positive")
    if range_multiplier <= 0:
        raise ValueError("range_multiplier must be positive")
    if len(candles) < 2:
        return None

    index = len(candles) - 1 if candle_index is None else candle_index
    if index <= 0:
        return None
    candle = candles[index]
    previous = candles[max(0, index - atr_period) : index]
    average_body = sum(abs(item.close - item.open) for item in previous) / len(previous)
    atr = average_true_range(candles[: index + 1], period=atr_period)
    body_size = abs(candle.close - candle.open)
    candle_range = candle.high - candle.low
    if atr <= 0 or average_body <= 0 or candle_range <= 0:
        return None

    bullish = direction == FairValueGapDirection.BULLISH and candle.close > candle.open
    bearish = direction == FairValueGapDirection.BEARISH and candle.close < candle.open
    if not (bullish or bearish):
        return None

    closes_near_extreme = (
        candle.close >= candle.low + candle_range * 0.7
        if bullish
        else candle.close <= candle.low + candle_range * 0.3
    )
    if (
        body_size >= average_body * body_multiplier
        and candle_range >= atr * range_multiplier
        and closes_near_extreme
    ):
        score = min(100.0, 50.0 + (body_size / max(average_body, 1e-9)) * 15.0)
        return DisplacementEvent(
            direction=direction,
            candle_index=index,
            timestamp=candle.open_time,
            strength_score=score,
            body_size=body_size,
            candle_range=candle_range,
            atr=atr,
        )
    return None
