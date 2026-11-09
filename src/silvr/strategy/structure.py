"""Causal market-structure helpers."""

from __future__ import annotations

from collections.abc import Sequence

from silvr.models import Candle
from silvr.strategy.models import (
    LiquiditySide,
    LiquiditySweep,
    MarketStructureShift,
    StructureShiftDirection,
    SwingPoint,
    SweepDirection,
)


def detect_swing_points(candles: Sequence[Candle], *, lookback: int = 3) -> list[SwingPoint]:
    """Detect causal swing highs/lows using only earlier candles.

    A candle is a swing high if its high is greater than the previous
    ``lookback`` highs. It is a swing low if its low is lower than the previous
    ``lookback`` lows. This avoids future-candle confirmation.
    """

    if lookback < 1:
        raise ValueError("lookback must be positive")

    swings: list[SwingPoint] = []
    for index in range(lookback, len(candles)):
        candle = candles[index]
        previous = candles[index - lookback : index]
        if candle.high > max(item.high for item in previous):
            swings.append(
                SwingPoint(
                    index=index,
                    timestamp=candle.open_time,
                    price=candle.high,
                    kind=LiquiditySide.BUY_SIDE,
                )
            )
        if candle.low < min(item.low for item in previous):
            swings.append(
                SwingPoint(
                    index=index,
                    timestamp=candle.open_time,
                    price=candle.low,
                    kind=LiquiditySide.SELL_SIDE,
                )
            )
    return swings


def detect_market_structure_shift(
    candles: Sequence[Candle],
    *,
    sweep: LiquiditySweep,
    swings: Sequence[SwingPoint],
) -> MarketStructureShift | None:
    """Detect a simple MSS on the latest candle after a sweep."""

    if not candles:
        return None
    latest_index = len(candles) - 1
    latest = candles[-1]

    if sweep.direction == SweepDirection.BULLISH:
        candidates = [
            swing
            for swing in swings
            if swing.kind == LiquiditySide.BUY_SIDE and swing.index < latest_index
        ]
        if not candidates:
            return None
        broken = candidates[-1]
        if latest.close > broken.price:
            return MarketStructureShift(
                direction=StructureShiftDirection.BULLISH,
                candle_index=latest_index,
                timestamp=latest.open_time,
                broken_level=broken.price,
            )
    if sweep.direction == SweepDirection.BEARISH:
        candidates = [
            swing
            for swing in swings
            if swing.kind == LiquiditySide.SELL_SIDE and swing.index < latest_index
        ]
        if not candidates:
            return None
        broken = candidates[-1]
        if latest.close < broken.price:
            return MarketStructureShift(
                direction=StructureShiftDirection.BEARISH,
                candle_index=latest_index,
                timestamp=latest.open_time,
                broken_level=broken.price,
            )
    return None
