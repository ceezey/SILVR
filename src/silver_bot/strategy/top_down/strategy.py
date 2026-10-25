"""Top-down order-block strategy: daily bias, 15m order blocks, 1m MSS entries (spec 3.2-3.4; TD-6, TD-8,
TD-11, TD-19, TD-22).

The engine calls step() once per 1m candle, oldest first. Higher-timeframe candles come from causal resamplers,
so a 15m/4H/1D candle is applied only at the first 1m candle opening at or after its close.

Order-block liquidity (TD-18): a level stops being liquidity as soon as price trades through it. A 4H level is
therefore marked taken by every closed 15m candle (StructureTracker.mark_taken), not only at the next 4H close.
Each 15m candle marks before a 4H candle closing at the same instant is applied, so a level is only checked by
candles that closed after it was recorded.

The sweep candle k-1 must take a level that was untaken when k-1 opened. When candle k closes, the live trackers
have already marked that level taken, and snapshotting every level on every 15m candle is too slow. So the levels
"untaken as of k-1's open" are rebuilt as the levels still untaken that the sweep reached
(StructureTracker.untaken_reached_by, a heap walk over the matches only) plus the levels taken since k-1 opened
(StructureTracker.last_taken): by the 15m updates of k-1 and k, and on 4H by the marks of k-1 and k and any 4H
update closing in that span. Those are passed as untaken copies; detect_order_block's own
`time < sweep.open_time` check drops the levels recorded after k-1 opened.

any_hour=True implements TD-6a and TD-6b of [[2026-10-25-top-down-ob-any-hour-design]]: there is no session
window, so a touch lives as long as its order block is active (the OB dying removes it) and plans carry the
session name "any_hour". The default keeps touches and MSS entries inside the Silver Bullet windows. With
first_touch_only (TD-6f) a touch ends earlier: the OB is dead after a second touch by a counted 1m candle.

skip_inside=True implements TD-6d and TD-6e: all four trackers ignore inside candles, and the OB pattern is the
last three 15m candles that counted, so an inside candle is never k and may sit between any two of them. ATR(14),
the FVG scan, OB invalidation and the 4H marks still use every closed 15m candle.

first_touch_only=True implements TD-6f: an OB is touched by the first 1m candle after it forms that overlaps its
zone (counted or inside). Then a counted 1m candle off the zone leaves it, and a later counted one on the zone is a
second touch that kills it (dropped from the book) before the MSS check, even on the MSS candle. Inside 1m
candles neither leave nor touch again. Every active OB is tracked, not only the best-ranked one touched.
first_touch_only is meant to be used with any_hour: a session window resets the touch lists when it changes, which
would re-arm touches.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

from silver_bot.data.resample import Resampler
from silver_bot.models import Candle
from silver_bot.strategy.models import FairValueGapDirection
from silver_bot.strategy.sessions import DEFAULT_SESSIONS, SilverBulletSessionEngine
from silver_bot.strategy.top_down.order_blocks import OrderBlock, OrderBookOfBlocks, detect_order_block, overlaps
from silver_bot.strategy.top_down.structure import StructureEvent, StructureTracker, SwingLevel
from silver_bot.strategy.top_down.targets import atr, final_target, stage2_level, unfilled_fvgs

_ATR_PERIOD = 14
_HTF_ORDER = ("1d", "4h", "15m")  # tie order for HTF candles closing at the same time
_MARK_ORDER = 0.5  # a 15m candle's 4H mark: after the 1D candle, before a 4H candle closing at the same time
_ANY_HOUR = "any_hour"


@dataclass(frozen=True, slots=True)
class EntryPlan:
    side: Literal["long", "short"]
    signal_time: datetime  # close_time of the 1m MSS candle
    raw_entry: float  # that candle's close, before costs
    stop: float
    final_target: float
    stage2: float | None
    session_name: str
    ob: OrderBlock
    reason: str


@dataclass(frozen=True, slots=True)
class StepResult:
    entry: EntryPlan | None
    skipped: str | None  # why a consumed MSS trigger did not become a plan
    events_15m: tuple[StructureEvent, ...]


class TopDownOBStrategy:
    """Per-1m state machine. It never sees the engine's position; the engine decides whether a plan is taken."""

    def __init__(
        self,
        *,
        stop_atr_multiple: float = 0.25,
        min_reward_r: float = 3.0,
        any_hour: bool = False,
        skip_inside: bool = False,
        first_touch_only: bool = False,
    ) -> None:
        self._stop_atr_multiple = stop_atr_multiple
        self._min_reward_r = min_reward_r
        self._any_hour = any_hour
        self._skip_inside = skip_inside
        self._first_touch_only = first_touch_only
        self._resamplers = [(tf, Resampler(tf)) for tf in _HTF_ORDER]
        self._daily = StructureTracker("1d", skip_inside=skip_inside)
        self._h4 = StructureTracker("4h", skip_inside=skip_inside)
        self._m15 = StructureTracker("15m", skip_inside=skip_inside)
        self._m1 = StructureTracker("1m", skip_inside=skip_inside)
        # (close_time, levels taken) of the latest 4H updates and marks / 15m updates, for the sweep's liquidity
        # rebuild. On 4H, k-1 and k each add a mark, and only the 4H candles holding k-1 and k can close after k-1
        # opens and by k's close (entries arrive in close-time order): four entries cover everything taken since
        # k-1 opened. With skip_inside, inside 15m candles between k-1 and k add marks too, so the 4H entries are
        # pruned by time instead (_prune_taken_4h); 15m entries are kept for counted candles only.
        self._taken_4h: deque[tuple[datetime, list[SwingLevel]]] = deque(maxlen=None if skip_inside else 4)
        self._taken_15m: deque[tuple[datetime, list[SwingLevel]]] = deque(maxlen=2)
        self._candles_15m: list[Candle] = []  # every closed 15m candle (ATR, FVGs, the default OB pattern)
        self._counted_15m: deque[Candle] = deque(maxlen=3)  # skip_inside: the OB pattern's counted candles (TD-6e)
        self._book = OrderBookOfBlocks()
        self._sessions = SilverBulletSessionEngine(sessions=DEFAULT_SESSIONS)
        self._window: tuple[str | None, datetime | None] | None = None  # (name, start_at) of the current session
        # OBs touched in the current session window. any_hour: a touch lives while its OB is active (TD-6b); with
        # first_touch_only an OB is dead after a second touch by a counted 1m candle (TD-6f). Use that flag only with
        # any_hour: a session window resets this list and would re-arm touches.
        self._touched: list[OrderBlock] = []
        self._left: list[OrderBlock] = []  # first_touch_only: touched OBs a counted 1m candle has since left

    def step(self, candle_1m: Candle, *, trading: bool = True) -> StepResult:
        """With trading=False (warm-up, TD-20) the touch and MSS bookkeeping still runs and an MSS still consumes
        its OB (TD-22), but no plan or skip is ever returned."""
        events_15m = self._apply_htf(candle_1m)
        mss = self._m1.update(candle_1m)

        best = self._book.best_touched(candle_1m)
        if best is None and not self._touched:
            return StepResult(None, None, events_15m)  # nothing to touch or trigger: skip the session lookup
        if self._any_hour:
            session_name, window = _ANY_HOUR, (_ANY_HOUR, None)
        else:
            session = self._sessions.evaluate(candle_1m.open_time)
            session_name = session.name
            window = (session.name, session.start_at) if session.is_active else None
        if window != self._window:
            self._window, self._touched, self._left = window, [], []
        if window is None:
            return StepResult(None, None, events_15m)
        if self._first_touch_only:
            self._track_touches(candle_1m)
        self._touched = [ob for ob in self._touched if ob.active]  # an invalidated OB takes its touch with it
        if not self._first_touch_only and best is not None and not any(ob is best for ob in self._touched):
            self._touched.append(best)
        if mss is None:
            return StepResult(None, None, events_15m)

        candidates = [ob for ob in self._touched if ob.active and ob.direction == mss.direction]
        if not candidates:
            return StepResult(None, None, events_15m)
        ob = max(candidates, key=lambda c: (c.rank, c.formed_at))
        self._book.consume(ob)  # TD-22: used up at its first MSS, whether or not a plan follows
        self._touched.remove(ob)
        if not trading:
            return StepResult(None, None, events_15m)
        plan = self._plan(ob, candle_1m, mss, session_name)
        if isinstance(plan, str):
            return StepResult(None, plan, events_15m)
        return StepResult(plan, None, events_15m)

    def _apply_htf(self, candle_1m: Candle) -> tuple[StructureEvent, ...]:
        """Steps 1-2: apply every newly closed 15m/4H/1D candle in close order, detect OBs, apply the bias."""
        closed = [
            (htf.candle.close_time, order, tf, htf.candle)
            for order, (tf, resampler) in enumerate(self._resamplers)
            for htf in resampler.push(candle_1m)
        ]
        closed += [(close_time, _MARK_ORDER, "mark", candle) for close_time, _, tf, candle in closed if tf == "15m"]
        if len(closed) > 1:
            closed.sort(key=lambda item: (item[0], item[1]))
        events: list[StructureEvent] = []
        for _, _, tf, candle in closed:
            if tf == "mark":
                self._h4.mark_taken(candle.high, candle.low)  # TD-18: a 15m candle takes 4H liquidity at its close
                self._taken_4h.append((candle.close_time, self._h4.last_taken))
            elif tf == "1d":
                self._daily.update(candle)
                self._book.on_bias(self._daily.trend)
            elif tf == "4h":
                self._h4.update(candle)
                self._taken_4h.append((candle.close_time, self._h4.last_taken))
            else:
                event = self._m15.update(candle)
                if event is not None:
                    events.append(event)
                counted = self._m15.last_counted  # always True without skip_inside
                if counted:
                    self._taken_15m.append((candle.close_time, self._m15.last_taken))  # inside ones take nothing
                    if self._skip_inside:
                        self._counted_15m.append(candle)
                self._candles_15m.append(candle)
                self._book.on_15m_close(candle)  # invalidation stays on every 15m close
                if counted:
                    self._detect()
                    if self._skip_inside:
                        self._prune_taken_4h(candle)
        return tuple(events)

    def _track_touches(self, candle_1m: Candle) -> None:
        """TD-6f: first touch, leave and second touch for every active OB (see the module docstring)."""
        counted = self._m1.last_counted
        self._left = [ob for ob in self._left if ob.active]
        for ob in self._book.active:
            on_zone = overlaps(ob, candle_1m)
            if not any(touched is ob for touched in self._touched):
                if on_zone:
                    self._touched.append(ob)
            elif not counted:
                continue  # an inside candle is part of the candle it sits in
            elif any(left is ob for left in self._left):
                if on_zone:
                    self._book.consume(ob)  # second touch: dead for entries, dropped like a consumed OB
            elif not on_zone:
                self._left.append(ob)

    def _prune_taken_4h(self, counted: Candle) -> None:
        """Drop the 4H entries no later rebuild reads: the next sweep is `counted` or later, and the rebuild only
        reads entries closing after the sweep opens.

        The inside candles that follow `counted` sit within its range, and its own mark came first, so their marks
        can only take levels recorded after it opened, which detect_order_block drops by time. They add nothing,
        but they (and the 4H closes during a long run of them) would push its mark out of a fixed-length deque.
        """
        while self._taken_4h and self._taken_4h[0][0] <= counted.open_time:
            self._taken_4h.popleft()

    def _detect(self) -> None:
        bias = self._daily.trend
        pattern = self._counted_15m if self._skip_inside else self._candles_15m
        if bias == "none" or len(pattern) < 3:
            return
        prev2, sweep, engulf = pattern[-3], pattern[-2], pattern[-1]
        side, reach = ("low", sweep.low) if bias == "bullish" else ("high", sweep.high)

        def levels_at_sweep_open(tracker: StructureTracker, taken: deque) -> list[SwingLevel]:
            levels = tracker.untaken_reached_by(side, reach)
            for close_time, levels_taken in taken:
                if close_time > sweep.open_time:
                    levels += [replace(level, taken=False) for level in levels_taken if level.side == side]
            return levels

        ob = detect_order_block(
            prev2,
            sweep,
            engulf,
            bias=bias,
            levels_4h=levels_at_sweep_open(self._h4, self._taken_4h),
            levels_15m=levels_at_sweep_open(self._m15, self._taken_15m),
        )
        if ob is not None:
            self._book.add(ob)

    def _plan(self, ob: OrderBlock, candle: Candle, mss: StructureEvent, session_name: str) -> EntryPlan | str:
        """Steps 6-7: the entry plan, or the reason it is skipped (fail closed on missing inputs)."""
        long = ob.direction == "bullish"
        side: Literal["long", "short"] = "long" if long else "short"
        if len(self._candles_15m) < _ATR_PERIOD + 1:
            return f"fewer than {_ATR_PERIOD + 1} closed 15m candles for ATR({_ATR_PERIOD})"
        margin = self._stop_atr_multiple * atr(self._candles_15m[-_ATR_PERIOD - 1 :], _ATR_PERIOD)
        entry = candle.close
        stop = ob.sweep_extreme - margin if long else ob.sweep_extreme + margin
        if (entry - stop if long else stop - entry) <= 0:
            return f"stop {stop:g} is not beyond entry {entry:g}"
        cap = self._h4.bullish_trigger if long else self._h4.bearish_trigger
        if cap is None or (cap <= entry if long else cap >= entry):
            return f"no 4H cap beyond entry {entry:g}"

        level_side: Literal["high", "low"] = "high" if long else "low"
        levels = self._m15.untaken_levels(level_side)
        fvg_direction = FairValueGapDirection.BEARISH if long else FairValueGapDirection.BULLISH
        fvgs = unfilled_fvgs(self._candles_15m, direction=fvg_direction)
        final = final_target(side=side, entry=entry, fvgs=fvgs, levels_15m=levels, cap=cap)
        reward_r = (final - entry) / (entry - stop)
        if reward_r < self._min_reward_r:
            return f"reward {reward_r:.2f}R is below the {self._min_reward_r:g}R minimum"
        stage2 = stage2_level(side=side, entry=entry, stop=stop, final=final, levels_15m=levels)
        reason = f"{ob.direction} OB (rank {ob.rank}) touched, 1m {mss.kind} in {session_name}, {reward_r:.2f}R"
        return EntryPlan(side, candle.close_time, entry, stop, final, stage2, session_name, ob, reason)
