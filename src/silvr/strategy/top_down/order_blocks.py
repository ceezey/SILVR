"""15m sweep-and-engulf order blocks and their lifecycle (spec 3.3; TD-4, TD-5, TD-18, TD-22).

detect_order_block looks only at the three candles and the level sequences it is given; it never reaches into
a tracker. The caller passes the levels as they stood when the sweep candle opened (TD-18), because a live
tracker will already have marked the swept level taken by the time the engulfing candle closes.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from silvr.models import Candle
from silvr.strategy.top_down.structure import SwingLevel, Trend


@dataclass(slots=True)
class OrderBlock:
    direction: Literal["bullish", "bearish"]
    zone_low: float
    zone_high: float
    sweep_extreme: float
    formed_at: datetime  # close_time of the engulfing candle
    rank: int  # 2 for a 4H sweep, 1 for a 15m sweep
    swept: SwingLevel
    active: bool = True


def detect_order_block(
    prev2: Candle,
    sweep: Candle,
    engulf: Candle,
    *,
    bias: Trend,
    levels_4h: Sequence[SwingLevel],
    levels_15m: Sequence[SwingLevel],
) -> OrderBlock | None:
    """The order block formed when `engulf` closes, or None.

    Levels of the wrong side are ignored. A 4H level beats a 15m one; among levels of one rank the one with
    the latest `time` is used (the first of them in sequence order on a tie).
    """
    if engulf.close_time is None:
        raise ValueError("detect_order_block needs an engulfing candle with a close_time")
    if bias == "bullish":
        direction, side = "bullish", "low"
        engulfs = engulf.close > engulf.open and engulf.close > max(prev2.high, sweep.high)
        zone_low, zone_high, extreme = sweep.low, max(prev2.high, sweep.high), sweep.low

        def swept(level: SwingLevel) -> bool:
            return sweep.low < level.price < sweep.close
    elif bias == "bearish":
        direction, side = "bearish", "high"
        engulfs = engulf.close < engulf.open and engulf.close < min(prev2.low, sweep.low)
        zone_low, zone_high, extreme = min(prev2.low, sweep.low), sweep.high, sweep.high

        def swept(level: SwingLevel) -> bool:
            return sweep.close < level.price < sweep.high
    else:
        return None
    if not engulfs:
        return None

    for rank, levels in ((2, levels_4h), (1, levels_15m)):
        hits = [
            level
            for level in levels
            if level.side == side and not level.taken and level.time < sweep.open_time and swept(level)
        ]
        if hits:
            level = max(hits, key=lambda hit: hit.time)
            return OrderBlock(direction, zone_low, zone_high, extreme, engulf.close_time, rank, level)
    return None


def overlaps(ob: OrderBlock, candle: Candle) -> bool:
    """The candle's range overlaps the OB's zone: a touch."""
    return candle.low <= ob.zone_high and candle.high >= ob.zone_low


def takes_previous_candle(prev2: Candle, sweep: Candle, bias: Trend) -> bool:
    """TD-25: the sweep trades past the candle before it, so it did not take a level that candle already broke."""
    return sweep.low < prev2.low if bias == "bullish" else sweep.high > prev2.high


def leaves_gap(ob: OrderBlock, candle: Candle) -> bool:
    """TD-26: the candle after the engulfing one stays clear of the zone: the imbalance."""
    return candle.low > ob.zone_high if ob.direction == "bullish" else candle.high < ob.zone_low


def closed_through(ob: OrderBlock, candle: Candle) -> bool:
    """The candle closed beyond the OB's far side."""
    return candle.close < ob.zone_low if ob.direction == "bullish" else candle.close > ob.zone_high


class OrderBookOfBlocks:
    """Active order blocks. Inactive ones are dropped so best_touched, run on every 1m candle, stays cheap."""

    def __init__(self) -> None:
        self._active: list[OrderBlock] = []

    def add(self, ob: OrderBlock) -> None:
        self._active.append(ob)

    def on_15m_close(self, candle: Candle) -> None:
        """Invalidate OBs this closed 15m candle closed through on their far side."""
        self._drop(lambda ob: closed_through(ob, candle))

    def on_bias(self, trend: Trend) -> None:
        self._drop(lambda ob: ob.direction != trend)

    def consume(self, ob: OrderBlock) -> None:
        self._drop(lambda kept: kept is ob)

    @property
    def active(self) -> tuple[OrderBlock, ...]:
        return tuple(self._active)

    def best_touched(self, candle_1m: Candle) -> OrderBlock | None:
        """Highest-rank active OB whose zone the candle's range overlaps; the newest formed_at at equal rank."""
        best = None
        for ob in self._active:
            if overlaps(ob, candle_1m):
                if best is None or (ob.rank, ob.formed_at) > (best.rank, best.formed_at):
                    best = ob
        return best

    def _drop(self, dead: Callable[[OrderBlock], bool]) -> None:
        for ob in self._active:
            if dead(ob):
                ob.active = False
        self._active = [ob for ob in self._active if ob.active]
