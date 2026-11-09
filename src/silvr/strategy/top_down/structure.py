"""Causal body-close market structure (spec 3.1; TD-2, TD-3, TD-18).

One StructureTracker runs per timeframe and is fed closed candles, oldest first.

Bookkeeping
-----------
* Swing high / swing low: the highest high / lowest low since the tracker started or since it was last
  restarted. The first candle seeds both. A bullish break restarts the swing high at the breaking candle;
  a bearish break restarts the swing low at the breaking candle.
* Protected level: one price, the protected low while the trend is bullish or the protected high while it
  is bearish. Each break sets it to the opposite extreme measured from the candle that set the broken
  level through the breaking candle (inclusive): for a bullish break the lowest low, for a bearish break
  the highest high. The broken level is the swing high (trend none or bullish) or the protected high
  (trend bearish); mirrored for a bearish break. On ties the earliest candle counts as the setter.
* Triggers: the bullish trigger is the protected high while the trend is bearish, otherwise the swing high;
  the bearish trigger is the protected low while the trend is bullish, otherwise the swing low. A candle
  breaks a trigger only when its close is beyond it. The check uses the triggers as they stood before the
  candle's own high and low are folded into the swing extremes, so a wick never breaks anything.
* Event: a break while the trend already points that way is a BoS, otherwise (trend none or opposite) a
  ChoCh. The event time is the breaking candle's close_time.
* Recorded levels (the liquidity of TD-18): every broken swing level and every protected level becomes a
  SwingLevel, stamped with the close_time of the update that recorded it (the moment it became known). A
  level turns taken once a later candle's high >= its price (highs) or low <= its price (lows); a level
  recorded on this update is checked from the next update on. A broken protected level is not recorded
  twice. Only untaken levels are kept, in a heap per side (highs by lowest price, lows by highest price),
  so an update only looks at the levels it actually takes. mark_taken applies the same check to a
  lower-timeframe candle's high and low without touching structure, so a level is taken as soon as any candle
  trades through it, not only at this timeframe's next close. last_taken lists the levels the most recent update
  or mark took, and untaken_reached_by finds the untaken levels a given price would take without sorting, so a
  caller can rebuild the levels that were untaken a few updates ago (the order-block sweep check of TD-18).
* Candle history: the (high, low) of every candle since the candle that set the current protected level,
  pruned after each break, so memory is bounded by the longest stretch between breaks.
* Inside candles (opt-in skip_inside, TD-6d of [[2026-10-25-top-down-ob-any-hour-design]]): a candle whose
  high <= and low >= the last counted candle's is part of that bigger candle and is ignored: no index, no
  history, no take, no break, and update returns None. Any candle whose wick or body goes outside counts and
  becomes the new reference. last_counted tells whether the most recent update counted (always True when
  skip_inside is off).
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from silvr.models import Candle

Trend = Literal["bullish", "bearish", "none"]


@dataclass(slots=True)
class SwingLevel:
    """A recorded swing price. taken flips to True once price trades through it."""

    price: float
    time: datetime
    side: Literal["high", "low"]
    taken: bool = False


@dataclass(frozen=True, slots=True)
class StructureEvent:
    kind: Literal["bos", "choch"]
    direction: Literal["bullish", "bearish"]
    level: float
    time: datetime


class StructureTracker:
    def __init__(self, timeframe: str, *, skip_inside: bool = False) -> None:
        self.timeframe = timeframe
        self._skip_inside = skip_inside
        self._reference: tuple[float, float] | None = None  # (high, low) of the last counted candle
        self.last_counted = True  # False when the most recent update was an ignored inside candle
        self.trend: Trend = "none"
        self._count = 0  # candles seen; the next candle's absolute index
        self._base = 0  # absolute index of _bars[0]
        self._bars: list[tuple[float, float]] = []  # (high, low)
        self._swing_high = self._swing_low = 0.0
        self._high_idx = self._low_idx = 0  # absolute index of the candle that set each swing
        self._protected: float | None = None
        self._protected_idx = 0
        self._seq = 0  # record order, to list levels newest first
        # (key, seq, level) heaps; key is price for highs and -price for lows, so the next level to be taken is first.
        self._untaken: dict[str, list[tuple[float, int, SwingLevel]]] = {"high": [], "low": []}
        self.last_taken: list[SwingLevel] = []  # levels the most recent update or mark_taken marked taken

    @property
    def bullish_trigger(self) -> float | None:
        if self._count == 0:
            return None
        return self._protected if self.trend == "bearish" else self._swing_high

    @property
    def bearish_trigger(self) -> float | None:
        if self._count == 0:
            return None
        return self._protected if self.trend == "bullish" else self._swing_low

    def untaken_levels(self, side: Literal["high", "low"]) -> list[SwingLevel]:
        """Recorded levels on this side that price has not traded through, newest first."""
        return [level for _, _, level in sorted(self._untaken[side], key=lambda entry: -entry[1])]

    def untaken_reached_by(self, side: Literal["high", "low"], price: float) -> list[SwingLevel]:
        """Untaken levels a candle reaching `price` would take (highs <= price, lows >= price), in no order.

        Walks only the matching top of the heap, so the cost is the number of matches.
        """
        heap = self._untaken[side]
        threshold = price if side == "high" else -price
        found: list[SwingLevel] = []
        stack = [0]
        while stack:
            i = stack.pop()
            if i < len(heap) and heap[i][0] <= threshold:
                found.append(heap[i][2])
                stack += (2 * i + 1, 2 * i + 2)
        return found

    def mark_taken(self, high: float, low: float) -> None:
        """Mark taken the untaken levels a candle with this high and low traded through, as update does.

        Structure (trend, swings, protected level, history) is untouched. last_taken lists the levels taken. A
        caller must only mark with candles that closed after the levels it may reach were recorded.
        """
        self.last_taken = []
        self._take("high", high)
        self._take("low", -low)

    def update(self, candle: Candle) -> StructureEvent | None:
        if candle.close_time is None:
            raise ValueError("StructureTracker needs candles with a close_time")
        self.last_taken = []
        if self._skip_inside and self._reference is not None:
            high, low = self._reference
            if candle.high <= high and candle.low >= low:
                self.last_counted = False
                return None
        self._reference = (candle.high, candle.low)
        self.last_counted = True
        index = self._count
        self._count += 1
        self._bars.append((candle.high, candle.low))
        if index == 0:
            self._swing_high, self._swing_low = candle.high, candle.low
            return None

        self._take("high", candle.high)
        self._take("low", -candle.low)

        bullish_trigger, bearish_trigger = self.bullish_trigger, self.bearish_trigger
        if candle.close > bullish_trigger:
            return self._break("bullish", candle, index, bullish_trigger)
        if candle.close < bearish_trigger:
            return self._break("bearish", candle, index, bearish_trigger)
        if candle.high > self._swing_high:
            self._swing_high, self._high_idx = candle.high, index
        if candle.low < self._swing_low:
            self._swing_low, self._low_idx = candle.low, index
        return None

    def _break(
        self, direction: Literal["bullish", "bearish"], candle: Candle, index: int, broken: float
    ) -> StructureEvent:
        bullish = direction == "bullish"
        kind = "bos" if self.trend == direction else "choch"
        reversal = self.trend == ("bearish" if bullish else "bullish")  # the broken level was the protected one
        if reversal:
            setter = self._protected_idx
        else:
            setter = self._high_idx if bullish else self._low_idx
            self._record(broken, "high" if bullish else "low", candle)

        # Opposite extreme from the broken level's candle through this one.
        window = self._bars[setter - self._base :]
        position, pick = (1, min) if bullish else (0, max)
        offset = pick(range(len(window)), key=lambda i: window[i][position])
        self.trend = direction
        self._protected, self._protected_idx = window[offset][position], setter + offset
        self._record(self._protected, "low" if bullish else "high", candle)

        if bullish:
            self._swing_high, self._high_idx = candle.high, index
        else:
            self._swing_low, self._low_idx = candle.low, index
        del self._bars[: self._protected_idx - self._base]
        self._base = self._protected_idx
        return StructureEvent(kind, direction, broken, candle.close_time)

    def _take(self, side: str, threshold: float) -> None:
        heap = self._untaken[side]
        while heap and heap[0][0] <= threshold:
            level = heapq.heappop(heap)[2]
            level.taken = True
            self.last_taken.append(level)

    def _record(self, price: float, side: Literal["high", "low"], candle: Candle) -> None:
        self._seq += 1
        key = price if side == "high" else -price
        heapq.heappush(self._untaken[side], (key, self._seq, SwingLevel(price, candle.close_time, side)))
