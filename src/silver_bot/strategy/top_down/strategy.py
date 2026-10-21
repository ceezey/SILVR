"""Top-down order-block strategy: daily bias, 15m order blocks, 1m MSS entries (spec 3.2-3.4; TD-6, TD-8,
TD-11, TD-19, TD-22).

The engine calls step() once per 1m candle, oldest first. Higher-timeframe candles come from causal resamplers,
so a 15m/4H/1D candle is applied only at the first 1m candle opening at or after its close.

Order-block liquidity (TD-18): the sweep candle k-1 must take a level that was untaken when k-1 opened. When
candle k closes, the live trackers have already marked that level taken, and snapshotting every level on every
15m candle is too slow. So the levels "untaken as of k-1's open" are rebuilt as the levels still untaken that the
sweep reached (StructureTracker.untaken_reached_by, a heap walk over the matches only) plus the levels taken by
the 15m/4H updates applied since k-1 opened (StructureTracker.last_taken, kept for the last two updates). Those
are passed as untaken copies; detect_order_block's own `time < sweep.open_time` check drops the levels recorded
after k-1 opened.
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
from silver_bot.strategy.top_down.order_blocks import OrderBlock, OrderBookOfBlocks, detect_order_block
from silver_bot.strategy.top_down.structure import StructureEvent, StructureTracker, SwingLevel
from silver_bot.strategy.top_down.targets import atr, final_target, stage2_level, unfilled_fvgs

_ATR_PERIOD = 14
_HTF_ORDER = ("1d", "4h", "15m")  # tie order for HTF candles closing at the same time


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

    def __init__(self, *, stop_atr_multiple: float = 0.25, min_reward_r: float = 3.0) -> None:
        self._stop_atr_multiple = stop_atr_multiple
        self._min_reward_r = min_reward_r
        self._resamplers = [(tf, Resampler(tf)) for tf in _HTF_ORDER]
        self._daily = StructureTracker("1d")
        self._h4 = StructureTracker("4h")
        self._m15 = StructureTracker("15m")
        self._m1 = StructureTracker("1m")
        # (close_time, levels taken) of the last two 4H / 15m updates, for the sweep's liquidity rebuild.
        self._taken_4h: deque[tuple[datetime, list[SwingLevel]]] = deque(maxlen=2)
        self._taken_15m: deque[tuple[datetime, list[SwingLevel]]] = deque(maxlen=2)
        self._candles_15m: list[Candle] = []
        self._book = OrderBookOfBlocks()
        self._sessions = SilverBulletSessionEngine(sessions=DEFAULT_SESSIONS)
        self._window: tuple[str | None, datetime | None] | None = None  # (name, start_at) of the current session
        self._touched: list[OrderBlock] = []  # OBs touched in the current session window

    def step(self, candle_1m: Candle, *, trading: bool = True) -> StepResult:
        events_15m = self._apply_htf(candle_1m)
        mss = self._m1.update(candle_1m)
        if not trading:
            return StepResult(None, None, events_15m)

        best = self._book.best_touched(candle_1m)
        if best is None and not self._touched:
            return StepResult(None, None, events_15m)  # nothing to touch or trigger: skip the session lookup
        session = self._sessions.evaluate(candle_1m.open_time)
        window = (session.name, session.start_at) if session.is_active else None
        if window != self._window:
            self._window, self._touched = window, []
        if window is None:
            return StepResult(None, None, events_15m)
        if best is not None and not any(ob is best for ob in self._touched):
            self._touched.append(best)
        if mss is None:
            return StepResult(None, None, events_15m)

        candidates = [ob for ob in self._touched if ob.active and ob.direction == mss.direction]
        if not candidates:
            return StepResult(None, None, events_15m)
        ob = max(candidates, key=lambda c: (c.rank, c.formed_at))
        self._book.consume(ob)  # TD-22: used up at its first MSS, whether or not a plan follows
        self._touched.remove(ob)
        plan = self._plan(ob, candle_1m, mss, session.name)
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
        if len(closed) > 1:
            closed.sort(key=lambda item: (item[0], item[1]))
        events: list[StructureEvent] = []
        for _, _, tf, candle in closed:
            if tf == "1d":
                self._daily.update(candle)
                self._book.on_bias(self._daily.trend)
            elif tf == "4h":
                self._h4.update(candle)
                self._taken_4h.append((candle.close_time, self._h4.last_taken))
            else:
                event = self._m15.update(candle)
                if event is not None:
                    events.append(event)
                self._taken_15m.append((candle.close_time, self._m15.last_taken))
                self._candles_15m.append(candle)
                self._book.on_15m_close(candle)
                self._detect()
        return tuple(events)

    def _detect(self) -> None:
        bias = self._daily.trend
        if bias == "none" or len(self._candles_15m) < 3:
            return
        prev2, sweep, engulf = self._candles_15m[-3:]
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
