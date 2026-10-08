"""Liquidity level and sweep detection."""

from __future__ import annotations

from collections.abc import Sequence

from silver_bot.models import Candle
from silver_bot.strategy.models import (
    LiquidityLevel,
    LiquiditySide,
    LiquiditySweep,
    SweepDirection,
    SwingPoint,
)


def liquidity_levels_from_swings(
    swings: Sequence[SwingPoint],
    *,
    lookback: int = 30,
    current_index: int | None = None,
) -> list[LiquidityLevel]:
    """Convert swing points into buy-side and sell-side liquidity levels."""

    if lookback < 1:
        raise ValueError("lookback must be positive")
    upper_bound = current_index if current_index is not None else float("inf")
    lower_bound = max(0, int(upper_bound) - lookback) if current_index is not None else 0
    levels: list[LiquidityLevel] = []
    for swing in swings:
        if not (lower_bound <= swing.index < upper_bound):
            continue
        levels.append(
            LiquidityLevel(
                price=swing.price,
                side=swing.kind,
                source="swing_high" if swing.kind == LiquiditySide.BUY_SIDE else "swing_low",
                candle_index=swing.index,
                timestamp=swing.timestamp,
            )
        )
    return levels


def detect_liquidity_sweep(
    candles: Sequence[Candle],
    *,
    levels: Sequence[LiquidityLevel],
    candle_index: int | None = None,
) -> LiquiditySweep | None:
    """Detect a sweep on the selected candle using prior liquidity levels."""

    if not candles:
        return None
    index = len(candles) - 1 if candle_index is None else candle_index
    if index <= 0:
        return None
    candle = candles[index]
    previous_close = candles[index - 1].close
    prior_levels = [level for level in levels if level.candle_index < index]

    sell_side = [level for level in prior_levels if level.side == LiquiditySide.SELL_SIDE]
    for level in sorted(sell_side, key=lambda item: abs(candle.low - item.price)):
        if previous_close >= level.price and candle.low < level.price and candle.close > level.price:
            return LiquiditySweep(
                direction=SweepDirection.BULLISH,
                level=level,
                candle_index=index,
                timestamp=candle.open_time,
                swept_price=candle.low,
                close_price=candle.close,
            )

    buy_side = [level for level in prior_levels if level.side == LiquiditySide.BUY_SIDE]
    for level in sorted(buy_side, key=lambda item: abs(candle.high - item.price)):
        if previous_close <= level.price and candle.high > level.price and candle.close < level.price:
            return LiquiditySweep(
                direction=SweepDirection.BEARISH,
                level=level,
                candle_index=index,
                timestamp=candle.open_time,
                swept_price=candle.high,
                close_price=candle.close,
            )
    return None


def nearest_opposing_liquidity(
    *,
    entry_price: float,
    direction: SweepDirection,
    levels: Sequence[LiquidityLevel],
) -> LiquidityLevel | None:
    """Return nearest target-side liquidity for the setup direction."""

    if direction == SweepDirection.BULLISH:
        targets = [
            level
            for level in levels
            if level.side == LiquiditySide.BUY_SIDE and level.price > entry_price
        ]
        return min(targets, key=lambda item: item.price - entry_price, default=None)
    targets = [
        level
        for level in levels
        if level.side == LiquiditySide.SELL_SIDE and level.price < entry_price
    ]
    return min(targets, key=lambda item: entry_price - item.price, default=None)
