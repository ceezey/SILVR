"""ATR, final target and stage 2 level for the top-down order-block strategy (TD-10, TD-21, TD-23)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from silver_bot.models import Candle
from silver_bot.strategy.fvg import detect_fair_value_gaps
from silver_bot.strategy.models import FairValueGap, FairValueGapDirection
from silver_bot.strategy.top_down.structure import SwingLevel


def atr(candles: Sequence[Candle], period: int = 14) -> float:
    """Simple mean of the last `period` true ranges (each against the previous close)."""

    if len(candles) < period + 1:
        raise ValueError(f"atr needs at least {period + 1} candles, got {len(candles)}")
    window = candles[-period - 1 :]
    total = 0.0
    for prev, cur in zip(window, window[1:]):
        total += max(cur.high - cur.low, abs(cur.high - prev.close), abs(cur.low - prev.close))
    return total / period


def unfilled_fvgs(candles_15m: Sequence[Candle], *, direction: FairValueGapDirection) -> list[FairValueGap]:
    """Gaps of `direction` not yet fully traded through by a later candle, newest first. O(n)."""

    gaps = [g for g in detect_fair_value_gaps(candles_15m) if g.direction == direction]
    bearish = direction == FairValueGapDirection.BEARISH
    later_high = float("-inf")  # highest high / lowest low of the candles after the current index
    later_low = float("inf")
    unfilled: list[FairValueGap] = []
    for index in range(len(candles_15m) - 1, -1, -1):
        if gaps and gaps[-1].candle_index == index:
            gap = gaps.pop()
            filled = later_high >= gap.upper_bound if bearish else later_low <= gap.lower_bound
            if not filled:
                unfilled.append(gap)
        later_high = max(later_high, candles_15m[index].high)
        later_low = min(later_low, candles_15m[index].low)
    return unfilled


def final_target(
    *,
    side: Literal["long", "short"],
    entry: float,
    fvgs: Sequence[FairValueGap],
    levels_15m: Sequence[SwingLevel],
    cap: float,
) -> float:
    """Nearest opposing FVG's far-side untaken 15m level within `cap`, else `cap`."""

    if side == "long":
        ahead = [g for g in fvgs if g.direction == FairValueGapDirection.BEARISH and g.lower_bound > entry]
        if not ahead:
            return cap
        edge = min(ahead, key=lambda g: g.lower_bound).upper_bound
        beyond = [lv.price for lv in levels_15m if lv.side == "high" and not lv.taken and edge < lv.price <= cap]
        return min(beyond, default=cap)
    ahead = [g for g in fvgs if g.direction == FairValueGapDirection.BULLISH and g.upper_bound < entry]
    if not ahead:
        return cap
    edge = max(ahead, key=lambda g: g.upper_bound).lower_bound
    beyond = [lv.price for lv in levels_15m if lv.side == "low" and not lv.taken and cap <= lv.price < edge]
    return max(beyond, default=cap)


def stage2_level(
    *,
    side: Literal["long", "short"],
    entry: float,
    stop: float,
    final: float,
    levels_15m: Sequence[SwingLevel],
) -> float | None:
    """Nearest untaken 15m level at least 1R from entry and strictly before `final`, else None."""

    risk = abs(entry - stop)
    if side == "long":
        prices = [lv.price for lv in levels_15m if lv.side == "high" and not lv.taken and entry + risk <= lv.price < final]
        return min(prices, default=None)
    prices = [lv.price for lv in levels_15m if lv.side == "low" and not lv.taken and final < lv.price <= entry - risk]
    return max(prices, default=None)
