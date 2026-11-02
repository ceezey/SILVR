"""The 1m entry of [[2026-11-02-top-down-ob-v4-design]]: CHoCH, 1m order-block box and retest (TD-30 to TD-35).

The first touch of a 15m OB starts a RetestSetup. The CHoCH level starts at the higher of the last swing high and
the touch candle's high, and rises when a new lowest low brings a higher high with it. The candle that made the lowest
low is the 1m OB candle. Its box runs from its low up to its high, cut down by the lowest low of the counted candles
after it: whatever price trades back into before the CHoCH is used up. The first counted candle closing above the
level is the CHoCH, and the box top is then the limit entry, live from the next candle on.

Shorts run the same comparisons on negated prices.
"""

from __future__ import annotations

from collections import deque

from silver_bot.models import Candle
from silver_bot.strategy.top_down.order_blocks import OrderBlock


class SwingTracker:
    """The last counted swing high and low: a candle beyond both counted neighbours. Feed counted candles only."""

    def __init__(self) -> None:
        self._window: deque[Candle] = deque(maxlen=3)
        self.high: float | None = None
        self.low: float | None = None

    def update(self, candle: Candle) -> None:
        self._window.append(candle)
        if len(self._window) < 3:
            return
        left, middle, right = self._window
        if middle.high > left.high and middle.high > right.high:
            self.high = middle.high
        if middle.low < left.low and middle.low < right.low:
            self.low = middle.low


class RetestSetup:
    """One 15m OB's wait for its CHoCH and then its fill. `entry` is None until the CHoCH candle has closed."""

    def __init__(self, ob: OrderBlock, touch: Candle, swing_high: float | None, swing_low: float | None) -> None:
        self.ob = ob
        self._sign = 1.0 if ob.direction == "bullish" else -1.0
        high, low, _ = self._oriented(touch)
        swing = swing_high if self._sign > 0 else (None if swing_low is None else -swing_low)
        self._lowest = low
        self._highest = high
        self._box_top = high
        self._level = high if swing is None else max(high, swing)
        self.entry: float | None = None

    @property
    def level(self) -> float:
        return self._sign * self._level

    def update(self, candle: Candle, counted: bool) -> None:
        """A candle closed before the CHoCH. Inside candles are part of the candle they sit in (TD-6d)."""
        if not counted:
            return
        high, low, close = self._oriented(candle)
        self._highest = max(self._highest, high)
        if low < self._lowest:
            self._lowest, self._box_top = low, high
            self._level = max(self._level, self._highest)
            return
        self._box_top = min(self._box_top, low)
        if close > self._level:
            self.entry = self._sign * self._box_top

    def fills(self, candle: Candle) -> bool:
        """Price traded strictly through the entry (TD-35). Only call this once `entry` is set."""
        return self._oriented(candle)[1] < self._sign * self.entry

    def _oriented(self, candle: Candle) -> tuple[float, float, float]:
        """(high, low, close) as a long sees them."""
        if self._sign > 0:
            return candle.high, candle.low, candle.close
        return -candle.low, -candle.high, -candle.close
