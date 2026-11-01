from datetime import UTC, datetime, timedelta

import pytest

from silver_bot.data import resample
from silver_bot.models import Candle
from silver_bot.strategy.top_down import StepResult, StructureTracker, TopDownOBStrategy, atr
from silver_bot.strategy.top_down import strategy as strategy_module
from silver_bot.strategy.top_down.order_blocks import OrderBlock
from silver_bot.strategy.top_down.structure import SwingLevel

M1 = timedelta(minutes=1)
M15 = timedelta(minutes=15)
DAY0 = datetime(2026, 1, 5, tzinfo=UTC)  # January: New York is UTC-5, so New York AM is 15:00-16:00 UTC
DAY1, DAY2, DAY3 = DAY0 + timedelta(days=1), DAY0 + timedelta(days=2), DAY0 + timedelta(days=3)
NY_AM = DAY3 + timedelta(hours=15)
MIRROR = 230.0  # short scenarios reflect every price around 115

Row = tuple[float, float, float, float]  # open, high, low, close


def one_minute(open_time: datetime, o: float, h: float, low: float, c: float) -> Candle:
    return Candle("BTCUSDT", "1m", open_time, o, h, low, c, 1.0, open_time + M1)


def as_15m(start: datetime, rows: list[Row]) -> list[Candle]:
    """The intended 15m candles (what the resampler must rebuild from expand_15m)."""
    return [
        Candle("BTCUSDT", "15m", start + i * M15, *row, 15.0, start + (i + 1) * M15 - timedelta(milliseconds=1))
        for i, row in enumerate(rows)
    ]


def expand_15m(start: datetime, rows: list[Row]) -> list[Candle]:
    """Each 15m row as 15 one-minute candles: the first carries the whole range, the rest sit flat at the close."""
    out = []
    for i, (o, h, low, c) in enumerate(rows):
        open_time = start + i * M15
        out.append(one_minute(open_time, o, h, low, c))
        out.extend(one_minute(open_time + j * M1, c, c, c, c) for j in range(1, 15))
    return out


def minutes(start: datetime, rows: list[Row]) -> list[Candle]:
    return [one_minute(start + i * M1, *row) for i, row in enumerate(rows)]


# Day 0 seeds the daily swing (high 111, low 109). Day 1 closes at 119 above 111: daily bullish ChoCh, protected
# low 109; the 4H swing high (the long cap) restarts at 120.
DAY0_ROWS: list[Row] = [(110, 111, 109, 110)] * 14
DAY1_ROWS: list[Row] = [(110, 112, 109.5, 111.5), (111.5, 114, 111, 113.5), (113.5, 117, 113, 116.5),
                        (116.5, 120, 116, 119.5), (119.5, 120, 118, 119)]
# Day 2: overlapping decline (no bearish FVG) from 119 to 105.5, a 15m bullish ChoCh recording the protected low
# 105.2, then k-2, the sweep k-1 (low 104.5 under 105.2, close 106 back above) and the engulfing k (close 108).
DECLINE: list[Row] = [(o, o + 0.3, o - 0.8, o - 0.5) for o in (119 - 0.5 * i for i in range(27))]
SETUP: list[Row] = [(105.5, 107.3, 105.4, 107.1), (107.1, 107.5, 106.6, 106.8), (106.8, 107.0, 104.5, 106.0),
                    (106.0, 108.2, 105.9, 108.0), (108, 108.6, 107.8, 108.3), (108, 108.6, 107.8, 108.3)]
ZONE = (104.5, 107.5)
SWEEP_LOW = 104.5
CAP = 120.0
# New York AM, day 3: a 1m descent into the zone (touch at the 5th candle), then a close above the last 1m
# lower high: the bullish MSS.
DESCENT: list[Row] = [(o, o + 0.1, o - 0.6, o - 0.5) for o in (110 - 0.5 * j for j in range(8))]
MSS: Row = (106.0, 107.3, 105.9, 107.2)


def day_rows(
    day2_close: float = 110.0, day0_rows: list[Row] = DAY0_ROWS, decline: list[Row] = DECLINE,
    setup: list[Row] = SETUP,
) -> tuple[list[Candle], list[Candle]]:
    """(1m candles, intended 15m candles) for days 0 to 2. day2_close is the close of day 2's last 15m candle."""
    last = [(108.3, max(108.5, day2_close + 0.2), min(108.2, day2_close - 0.2), day2_close)]
    late = DAY2 + timedelta(hours=23, minutes=45)
    blocks = [(DAY0, day0_rows), (DAY1, DAY1_ROWS), (DAY2, decline + setup), (late, last)]
    ones = [c for start, rows in blocks for c in expand_15m(start, rows)]
    fifteens = [c for start, rows in blocks for c in as_15m(start, rows)]
    return ones, fifteens


def run(candles: list[Candle], *, trading: bool = True, strategy: TopDownOBStrategy | None = None) -> list[StepResult]:
    strategy = strategy or TopDownOBStrategy()
    return [strategy.step(c, trading=trading) for c in candles]


def entries(results: list[StepResult]) -> list:
    return [r.entry for r in results if r.entry is not None]


def bullish_1m_breaks(candles: list[Candle]) -> list[int]:
    """Indices of 1m candles that make a bullish break, from an independent 1m tracker."""
    tracker = StructureTracker("1m")
    return [i for i, c in enumerate(candles) if (e := tracker.update(c)) is not None and e.direction == "bullish"]


def mirror(candles: list[Candle]) -> list[Candle]:
    return [
        Candle(c.symbol, c.timeframe, c.open_time, MIRROR - c.open, MIRROR - c.low, MIRROR - c.high,
               MIRROR - c.close, c.volume, c.close_time)
        for c in candles
    ]


def long_scenario() -> tuple[list[Candle], list[Candle]]:
    ones, fifteens = day_rows()
    return ones + minutes(NY_AM, DESCENT + [MSS]), fifteens


def test_long_plan_on_touch_then_1m_mss_in_session() -> None:
    candles, fifteens = long_scenario()
    results = run(candles)

    plans = entries(results)
    assert len(plans) == 1
    plan = plans[0]
    assert results[-1].entry is plan  # the MSS candle is the last one
    assert plan.side == "long"
    assert plan.signal_time == candles[-1].close_time
    assert plan.raw_entry == MSS[3]
    assert plan.stop == pytest.approx(SWEEP_LOW - 0.25 * atr(fifteens[-15:]))
    # No bearish FVG lies above entry, so the final target is the 4H cap (TD-21).
    assert plan.final_target == CAP
    risk = plan.raw_entry - plan.stop
    assert plan.stage2 is not None and plan.raw_entry + risk <= plan.stage2 < plan.final_target
    assert plan.session_name == "new_york_am"
    assert (plan.ob.zone_low, plan.ob.zone_high) == ZONE
    assert plan.ob.swept.price == 105.2 and plan.ob.rank == 1
    assert not plan.ob.active


def test_short_mirror_plan() -> None:
    candles, fifteens = long_scenario()
    long_plan = entries(run(candles))[0]

    plans = entries(run(mirror(candles)))

    assert len(plans) == 1
    plan = plans[0]
    assert plan.side == "short"
    assert plan.ob.direction == "bearish"
    assert plan.signal_time == long_plan.signal_time
    assert plan.raw_entry == pytest.approx(MIRROR - long_plan.raw_entry)
    assert plan.stop == pytest.approx(MIRROR - SWEEP_LOW + 0.25 * atr(fifteens[-15:]))
    assert plan.final_target == pytest.approx(MIRROR - CAP)
    assert plan.stage2 == pytest.approx(MIRROR - long_plan.stage2)
    assert plan.session_name == "new_york_am"


def test_no_trade_before_daily_trend_exists() -> None:
    # A day-0 wick to 130 means day 1's close of 119 never breaks the daily swing high: the daily trend stays none.
    ones, _ = day_rows(day0_rows=[(110, 130, 109, 110)] + DAY0_ROWS[1:])
    results = run(ones + minutes(NY_AM, DESCENT + [MSS]))

    assert entries(results) == []
    assert all(r.skipped is None for r in results)


def test_touch_outside_session_does_not_trigger() -> None:
    ones, _ = day_rows()
    early = NY_AM - timedelta(minutes=20)  # 09:40 New York: the same touch and MSS, before the window opens
    results = run(ones + minutes(early, DESCENT + [MSS]))

    assert entries(results) == []
    assert all(r.skipped is None for r in results)


def test_mss_before_touch_does_not_trigger() -> None:
    ones, _ = day_rows()
    above = DESCENT[:4]  # lows stay above the zone high 107.5
    early_mss: Row = (108.0, 110.4, 107.9, 110.3)  # closes above the 1m swing high 110.2: a bullish MSS, no touch yet
    into_zone: list[Row] = [(110.3, 110.3, 107.0, 107.1), (107.1, 107.2, 106.5, 106.6), (106.6, 106.7, 106.0, 106.1)]
    candles = ones + minutes(NY_AM, above + [early_mss] + into_zone)
    results = run(candles)

    assert [i for i in bullish_1m_breaks(candles) if i >= len(ones)] == [len(ones) + len(above)]
    assert entries(results) == []
    assert all(r.skipped is None for r in results)


def test_reward_below_3r_is_skipped_and_ob_consumed() -> None:
    ones, _ = day_rows()
    far_mss: Row = (106.0, 111.1, 105.9, 111.0)  # entry 111: (120 - 111) / (111 - ~104.2) < 3
    # Back into the zone with lower 1m highs, then a close above the last one: a second, 9R MSS.
    second_try = [(o, o + 0.1, o - 0.6, o - 0.5) for o in (110.5 - 0.5 * j for j in range(12))]
    second_mss: Row = (104.5, 105.8, 104.4, 105.7)
    candles = ones + minutes(NY_AM, DESCENT + [far_mss] + second_try + [second_mss])
    results = run(candles)

    skipped = [r.skipped for r in results if r.skipped is not None]
    assert len(skipped) == 1 and "3R" in skipped[0]
    assert results[len(ones) + len(DESCENT)].skipped == skipped[0]  # on the far MSS candle
    assert entries(results) == []
    assert len(candles) - 1 in bullish_1m_breaks(candles)  # the second MSS is real; the OB is just gone


def test_bias_flip_keeps_position_and_drops_old_obs() -> None:
    # Day 2 closes at 105.6: below the daily protected low 109 (daily bearish ChoCh when day 3 starts) but above
    # the zone low 104.5, so no 15m close invalidates the OB; only the bias flip removes it.
    ones, _ = day_rows(day2_close=105.6)
    # In the zone from the open: two lower 1m highs, then a close above the last one (a real bullish MSS)...
    session: list[Row] = [(105.6, 105.7, 105.0, 105.1), (105.1, 105.2, 104.6, 104.7), (104.7, 105.9, 104.6, 105.8)]
    # ...then a rally so the 15:00 15m candle closes at 109, above the 15m swing high 108.6.
    rally: list[Row] = [(105.8, 109.1, 105.7, 109.0)] + [(109.0, 109.1, 108.9, 109.0)] * 12
    candles = ones + minutes(NY_AM, session + rally)
    strategy = TopDownOBStrategy()
    results = run(candles, strategy=strategy)

    assert len(ones) + 2 in bullish_1m_breaks(candles)
    assert entries(results) == []
    assert all(r.skipped is None for r in results)
    assert strategy._daily.trend == "bearish"
    # 15m structure events keep flowing after the flip, so the engine can still manage an open long.
    assert results[-1].events_15m and results[-1].events_15m[0].direction == "bullish"


def test_warmup_step_never_returns_plan() -> None:
    candles, _ = long_scenario()
    results = run(candles, trading=False)

    assert entries(results) == []
    assert all(r.skipped is None for r in results)


def test_htf_candles_never_used_before_close(monkeypatch: pytest.MonkeyPatch) -> None:
    now: list[datetime] = []
    seen: list[tuple[datetime, Candle]] = []
    push, update = resample.Resampler.push, StructureTracker.update

    def recording_push(self, candle):
        now.append(candle.open_time)
        return push(self, candle)

    def recording_update(self, candle):
        if self.timeframe != "1m":
            seen.append((now[-1], candle))
        return update(self, candle)

    monkeypatch.setattr(strategy_module.Resampler, "push", recording_push)
    monkeypatch.setattr(strategy_module.StructureTracker, "update", recording_update)
    candles, _ = long_scenario()
    assert len(entries(run(candles))) == 1

    assert {c.timeframe for _, c in seen} == {"15m", "4h", "1d"}
    assert all(c.close_time < open_time for open_time, c in seen)


# TD-18 at 15m resolution. After days 0 and 1 the 4H tracker holds the untaken low 109 (the protected low of
# day 1's 4H ChoCh, recorded at day 1 03:59:59.999). Day 2's first three 15m candles (k-2, the sweep k-1 and the
# engulfing k) all sit inside the still-forming 00:00-04:00 4H candle.
SWEEP_4H: Row = (112.0, 112.2, 108.5, 110.0)  # low 108.5 under 109, close back above it
ENGULF_4H: Row = (110.0, 113.0, 109.8, 112.8)  # bullish, closes above both earlier highs (112.5)


def obs_after_4h_sweep(
    prev2_low: float, start: datetime = DAY2, inside: tuple[Row, ...] = (), skip_inside: bool = False,
    strategy: TopDownOBStrategy | None = None,
) -> list:
    """The active OBs once k closes, with k-2's low at prev2_low and k-2 opening at start (inside: 15m rows
    between k-1 and k)."""
    days = [c for begin, rows in ((DAY0, DAY0_ROWS), (DAY1, DAY1_ROWS)) for c in expand_15m(begin, rows)]
    day2 = expand_15m(start, [(112.0, 112.5, prev2_low, 112.0), SWEEP_4H, *inside, ENGULF_4H])
    strategy = strategy or TopDownOBStrategy(skip_inside=skip_inside)
    emit_k = one_minute(start + (3 + len(inside)) * M15, 112.8, 112.8, 112.8, 112.8)
    run(days + day2 + [emit_k], strategy=strategy)
    return strategy._book._active


def test_4h_sweep_forms_rank_2_ob() -> None:
    (ob,) = obs_after_4h_sweep(prev2_low=109.5)  # k-2 stays above 109: the level is untaken when k-1 opens

    assert ob.rank == 2
    assert (ob.swept.price, ob.swept.side) == (109, "low")
    assert ob.swept.time == DAY1 + timedelta(hours=4) - timedelta(milliseconds=1)  # the 4H level, not the 15m 109
    assert (ob.zone_low, ob.zone_high) == (108.5, 112.5)


def test_4h_sweep_by_last_15m_candle_of_a_4h_candle_forms_rank_2_ob() -> None:
    # k-1 is the 03:45 candle: its mark, then the 4H candle closing at the same instant, then k's mark are all
    # applied after k-1 opened, and the level k-1 took must still be found.
    (ob,) = obs_after_4h_sweep(prev2_low=109.5, start=DAY2 + timedelta(hours=3, minutes=30))

    assert (ob.rank, ob.swept.price) == (2, 109)


def test_4h_level_taken_inside_forming_4h_candle_is_not_swept() -> None:
    # k-2 wicks to 108.8 first: the 4H level is taken before k-1 opens, though its 4H candle has not closed.
    assert [ob.rank for ob in obs_after_4h_sweep(prev2_low=108.8)] == []


def test_4h_level_recorded_at_a_close_is_only_taken_by_later_15m_candles() -> None:
    # Two 4H candles: the second closes at 111.2 above the 4H swing high 111 (a ChoCh recording the high 111 at
    # 07:59:59.999). Its last 15m candle (07:45) closes at that same instant with a high of 111.5.
    first = expand_15m(DAY0, [(110, 111, 109, 110)] * 16)
    second = expand_15m(DAY0 + timedelta(hours=4), [(110, 111.5, 110, 111.2)] * 16)
    # The 08:00 15m candle trades through 111 while its 4H candle is still forming.
    third = expand_15m(DAY0 + timedelta(hours=8), [(111.2, 111.6, 111.0, 111.2)])
    strategy = TopDownOBStrategy()
    run(first + second + third[:1], strategy=strategy)  # 08:00 emits the second 4H candle

    assert [level.price for level in strategy._h4.untaken_levels("high")] == [111]  # not taken by the 07:45 candle

    run(third[1:] + [one_minute(DAY0 + timedelta(hours=8, minutes=15), 111.2, 111.2, 111.2, 111.2)], strategy=strategy)

    assert strategy._h4.untaken_levels("high") == []


# A 1m descent from 110.5 into the zone, then a close above the last 1m lower high at 105.7: a bullish MSS deep
# in the zone (entry 105.7, about 1.54 of risk).
DEEP_DESCENT: list[Row] = [(o, o + 0.1, o - 0.6, o - 0.5) for o in (110.5 - 0.5 * j for j in range(12))]
DEEP_MSS: Row = (104.5, 105.8, 104.4, 105.7)


def test_ob_consumed_by_mss_during_warmup_is_not_tradeable_after() -> None:
    # The touch and the first MSS happen during warm-up (TD-20): the OB is used up there (TD-22), so the second
    # MSS in the same session, now trading, plans nothing.
    ones, _ = day_rows()
    warm = ones + minutes(NY_AM, DESCENT + [MSS])
    live = minutes(NY_AM + (len(DESCENT) + 1) * M1, DEEP_DESCENT + [DEEP_MSS])
    strategy = TopDownOBStrategy()

    assert all(r.entry is None and r.skipped is None for r in run(warm, trading=False, strategy=strategy))
    results = run(live, strategy=strategy)

    assert len(warm) + len(live) - 1 in bullish_1m_breaks(warm + live)  # the second MSS is real
    assert entries(results) == []
    assert all(r.skipped is None for r in results)


def test_final_target_is_15m_high_beyond_unfilled_bearish_fvg() -> None:
    # Decline candle 17 tops at 110.6, under candle 15's low 110.7: a bearish 15m FVG 110.6-110.7 above the entry
    # that no later candle trades back up through. The first untaken 15m high beyond it is 111.3, below the 4H cap.
    assert DECLINE[15][2] == 110.7 and DECLINE[17] == (110.5, 110.8, 109.7, 110.0)
    gapped = [*DECLINE[:17], (110.5, 110.6, 109.7, 110.0), *DECLINE[17 + 1 :]]

    for decline, target in ((DECLINE, CAP), (gapped, 111.3)):  # no FVG: the cap (TD-21)
        ones, _ = day_rows(decline=decline)
        (plan,) = entries(run(ones + minutes(NY_AM, DEEP_DESCENT + [DEEP_MSS])))

        assert (plan.side, plan.raw_entry) == ("long", 105.7)
        assert plan.final_target == target


# any_hour (TD-6a, TD-6b): no session window, so a touch lives as long as its OB.
def test_any_hour_touch_and_mss_outside_session_triggers() -> None:
    ones, _ = day_rows()
    early = NY_AM - timedelta(hours=1)  # 09:00 New York: outside every window; 9 candles stay inside one 15m period,
    # so no 15m candle closes before the MSS and the ATR (hence the stop) matches the in-session run
    candles = ones + minutes(early, DESCENT + [MSS])
    in_session = entries(run(ones + minutes(NY_AM, DESCENT + [MSS])))[0]

    plans = entries(run(candles, strategy=TopDownOBStrategy(any_hour=True)))

    assert len(plans) == 1
    plan = plans[0]
    assert plan.session_name == "any_hour"
    assert plan.signal_time == candles[-1].close_time
    assert (plan.raw_entry, plan.stop, plan.final_target) == (in_session.raw_entry, in_session.stop, in_session.final_target)
    assert (plan.ob.zone_low, plan.ob.zone_high) == ZONE
    assert "in any_hour" in plan.reason
    assert entries(run(candles)) == []  # the default variant still ignores it


def test_short_mirror_any_hour() -> None:
    ones, _ = day_rows()
    candles = mirror(ones + minutes(NY_AM - timedelta(hours=1), DESCENT + [MSS]))
    plans = entries(run(candles, strategy=TopDownOBStrategy(any_hour=True)))
    assert len(plans) == 1 and plans[0].side == "short" and plans[0].session_name == "any_hour"


EARLY = NY_AM - timedelta(hours=5)  # 05:00 New York, on a 15m boundary: outside every window
# A steep 1m descent whose last candle (low 107.4) touches the zone high 107.5. The 1m bullish trigger is then
# 107.9 (the high of the candle holding the broken swing low), so a later MSS keeps the reward above 3R.
TOUCH: list[Row] = [(110.0, 110.1, 109.4, 109.5), (109.5, 109.6, 108.4, 108.5), (107.8, 107.9, 107.6, 107.7),
                    (107.7, 107.8, 107.4, 107.5)]


def test_any_hour_touch_survives_hours_away_from_zone() -> None:
    ones, _ = day_rows()
    drift: list[Row] = [(107.7, 107.8, 107.6, 107.7)] * 130  # lows stay above 107.5; no bullish break
    mss: Row = (107.7, 108.1, 107.7, 108.0)  # the first close above the 1m trigger 107.9
    candles = ones + minutes(EARLY, TOUCH + drift + [mss])

    assert [i for i in bullish_1m_breaks(candles) if i >= len(ones) + len(TOUCH)] == [len(candles) - 1]
    plans = entries(run(candles, strategy=TopDownOBStrategy(any_hour=True)))
    assert len(plans) == 1 and (plans[0].ob.zone_low, plans[0].ob.zone_high) == ZONE
    assert entries(run(candles)) == []


def invalidated_touch_candles() -> list[Candle]:
    """A touch, a 15m candle closing below the zone low 104.5 (the OB dies), then a bullish 1m MSS."""
    ones, _ = day_rows()
    pad: list[Row] = [(107.5, 107.5, 107.5, 107.5)] * (15 - len(TOUCH))  # fill the 15m period holding the touch
    crash = expand_15m(EARLY + M15, [(107.5, 107.6, 104.0, 104.2)])
    after: list[Row] = [(104.2, 108.0, 104.1, 107.9)]  # closes above the 1m trigger: a bullish MSS
    candles = ones + minutes(EARLY, TOUCH + pad) + crash + minutes(EARLY + 2 * M15, after)
    assert len(candles) - 1 in bullish_1m_breaks(candles)
    return candles


def test_any_hour_touch_dies_with_its_ob() -> None:
    plans = entries(run(invalidated_touch_candles(), strategy=TopDownOBStrategy(any_hour=True)))

    assert all((p.ob.zone_low, p.ob.zone_high) != ZONE for p in plans)


def test_any_hour_drops_inactive_touched_obs() -> None:
    strategy = TopDownOBStrategy(any_hour=True)
    run(invalidated_touch_candles(), strategy=strategy)

    assert strategy._touched == []


def test_any_hour_warmup_touch_carries_into_trading() -> None:
    ones, _ = day_rows()
    start = EARLY
    strategy = TopDownOBStrategy(any_hour=True)
    run(ones + minutes(start, TOUCH), trading=False, strategy=strategy)

    mss_candles = minutes(start + len(TOUCH) * M1, [(107.5, 108.1, 107.4, 108.0)])
    plans = entries(run(mss_candles, strategy=strategy))

    assert len(plans) == 1 and (plans[0].ob.zone_low, plans[0].ob.zone_high) == ZONE


# Inside candles (TD-6d, TD-6e): a candle inside the last counted candle is ignored by structure and by the OB
# pattern.
def test_v2_trackers_skip_inside_on_every_timeframe() -> None:
    strategy = TopDownOBStrategy(skip_inside=True)
    trackers = (strategy._daily, strategy._h4, strategy._m15, strategy._m1)

    assert all(tracker._skip_inside for tracker in trackers)
    assert not any(tracker._skip_inside for tracker in (TopDownOBStrategy()._m15, TopDownOBStrategy()._m1))


def test_v2_mss_ignores_swings_inside_a_big_1m_candle() -> None:
    # A rally to 110.4 makes the 1m trend bullish (protected low 107.6) without touching the zone. The big candle
    # wicks into the zone to 105 and closes back above 107.6; the next three sit inside it. Read on every candle,
    # they make a bearish ChoCh and BoS, then close above 107.75, a high only inside candles made: a bullish MSS.
    ones, _ = day_rows()
    rally: list[Row] = [(110.0, 110.1, 108.6, 108.7), (108.7, 108.8, 107.6, 107.7), (107.7, 110.5, 107.7, 110.4)]
    big: Row = (107.8, 108.5, 105.0, 107.7)
    inside: list[Row] = [(107.7, 107.75, 107.0, 107.1), (107.1, 107.2, 106.4, 106.5), (106.5, 107.9, 106.4, 107.8)]
    candles = ones + minutes(EARLY, rally + [big] + inside)
    assert len(candles) - 1 in bullish_1m_breaks(candles)

    assert len(entries(run(candles, strategy=TopDownOBStrategy(any_hour=True)))) == 1
    assert entries(run(candles, strategy=TopDownOBStrategy(any_hour=True, skip_inside=True))) == []


def test_v2_inside_15m_candle_cannot_complete_an_ob() -> None:
    # In place of the engulfing candle, a bullish candle inside the sweep; the next counted candle is bearish.
    inside_k: Row = (106.0, 106.9, 104.8, 106.8)
    ones, _ = day_rows(setup=SETUP[:3] + [inside_k, (107.2, 107.3, 106.9, 107.0)])
    strategy = TopDownOBStrategy(any_hour=True, skip_inside=True)
    run(ones, strategy=strategy)

    assert strategy._book._active == []
    assert entries(run(minutes(NY_AM, DESCENT + [MSS]), strategy=strategy)) == []
    control, _ = long_scenario()
    assert len(entries(run(control, strategy=TopDownOBStrategy(any_hour=True, skip_inside=True)))) == 1


def test_v2_ob_forms_across_inside_15m_candles() -> None:
    inside: list[Row] = [(106.0, 106.9, 104.8, 106.5), (106.5, 106.8, 105.0, 106.2)]  # within the sweep 104.5-107
    ones, _ = day_rows(setup=SETUP[:3] + inside + SETUP[3:])
    strategy = TopDownOBStrategy(any_hour=True, skip_inside=True)
    run(ones, strategy=strategy)

    (ob,) = strategy._book._active
    assert (ob.zone_low, ob.zone_high) == ZONE
    assert (ob.swept.price, ob.rank) == (105.2, 1)  # the 15m protected low the sweep took
    plans = entries(run(minutes(NY_AM, DESCENT + [MSS]), strategy=strategy))
    assert len(plans) == 1 and plans[0].ob is ob


def test_v2_4h_sweep_across_inside_15m_candles_forms_rank_2_ob() -> None:
    # Three inside candles between k-1 and k add three 4H marks: k-1's mark, the one holding the swept 4H level,
    # must still be in the liquidity rebuild when k closes.
    inside = ((110.0, 110.5, 109.0, 110.2),) * 3

    strategy = TopDownOBStrategy(skip_inside=True)
    (ob,) = obs_after_4h_sweep(prev2_low=109.5, inside=inside, skip_inside=True, strategy=strategy)

    assert (ob.rank, ob.swept.price) == (2, 109)
    # Pruned by time at every counted 15m candle: only the entries closing after the last counted candle (k, the
    # engulfing one) opened remain, which is k's own mark. Unpruned, every mark since day 0 would be held.
    assert len(strategy._taken_4h) == 1
    assert ob.swept.time == DAY1 + timedelta(hours=4) - timedelta(milliseconds=1)
    assert (ob.zone_low, ob.zone_high) == (108.5, 112.5)


# First touch only (TD-6f): leaving the zone and coming back, judged on counted 1m candles, kills the OB.
def v2() -> TopDownOBStrategy:
    return TopDownOBStrategy(any_hour=True, skip_inside=True, first_touch_only=True)


LEAVE: Row = (107.6, 107.85, 107.6, 107.8)  # counted (high above the touch candle's), low above the zone high 107.5
RETURN: Row = (107.8, 107.85, 107.45, 107.5)  # counted (low under the leave candle's), back in the zone
MSS_1M: Row = (107.5, 108.1, 107.5, 108.0)  # the first close above the 1m trigger 107.9


def test_v2_mss_during_first_touch_enters() -> None:
    ones, _ = day_rows()
    plans = entries(run(ones + minutes(NY_AM - timedelta(hours=1), DESCENT + [MSS]), strategy=v2()))

    assert len(plans) == 1 and (plans[0].ob.zone_low, plans[0].ob.zone_high) == ZONE


def test_v2_second_touch_kills_the_ob() -> None:
    ones, _ = day_rows()
    after = minutes(EARLY, TOUCH + [LEAVE, RETURN, MSS_1M])
    assert len(ones) + len(after) - 1 in bullish_1m_breaks(ones + after)
    strategy = v2()
    run(ones, strategy=strategy)
    (ob,) = strategy._book._active

    assert entries(run(after, strategy=strategy)) == []
    assert not ob.active
    control = TopDownOBStrategy(any_hour=True, skip_inside=True)
    assert len(entries(run(ones + after, strategy=control))) == 1


def test_v2_inside_1m_candles_neither_leave_nor_retouch() -> None:
    # Candle A wicks into the zone; B sits above the zone and C back in it, both inside A; then a counted MSS.
    ones, _ = day_rows()
    big: Row = (107.7, 107.85, 107.0, 107.2)
    inside: list[Row] = [(107.6, 107.8, 107.55, 107.7), (107.7, 107.8, 107.1, 107.3)]
    mss: Row = (107.3, 108.1, 107.2, 108.0)
    candles = ones + minutes(EARLY, TOUCH[:3] + [big] + inside + [mss])

    plans = entries(run(candles, strategy=v2()))

    assert len(plans) == 1 and (plans[0].ob.zone_low, plans[0].ob.zone_high) == ZONE
    # Counted, B leaves and C touches again.
    assert entries(run(candles, strategy=TopDownOBStrategy(any_hour=True, first_touch_only=True))) == []


def test_v2_retouch_candle_that_makes_the_mss_does_not_enter() -> None:
    ones, _ = day_rows()
    retouch_mss: Row = (107.8, 108.1, 107.4, 108.0)  # back in the zone and closing above the 1m trigger 107.9
    candles = ones + minutes(EARLY, TOUCH + [LEAVE, retouch_mss])
    assert len(candles) - 1 in bullish_1m_breaks(candles)

    assert entries(run(candles, strategy=v2())) == []
    assert len(entries(run(candles, strategy=TopDownOBStrategy(any_hour=True, skip_inside=True)))) == 1


def test_v2_warmup_leave_carries_into_trading_second_touch() -> None:
    ones, _ = day_rows()
    strategy = v2()
    run(ones + minutes(EARLY, TOUCH + [LEAVE]), trading=False, strategy=strategy)
    (ob,) = strategy._book.active

    results = run(minutes(EARLY + 5 * M1, [RETURN, MSS_1M]), strategy=strategy)  # trading=True

    assert entries(results) == []
    assert not ob.active  # the warm-up state remembered the touch and the leave, so the return killed it


def test_v2_warmup_touch_then_mss_without_leaving_enters() -> None:
    ones, _ = day_rows()
    strategy = v2()
    run(ones + minutes(EARLY, TOUCH), trading=False, strategy=strategy)

    plans = entries(run(minutes(EARLY + len(TOUCH) * M1, [MSS_1M]), strategy=strategy))

    assert len(plans) == 1 and (plans[0].ob.zone_low, plans[0].ob.zone_high) == ZONE


def test_v2_second_touch_kills_only_the_ob_that_was_left() -> None:
    # Built with a second OrderBlock added to the book after the HTF setup: rank 2 and a zone wider than every 1m
    # candle below, so it is touched at once and never left. The real rank 1 OB (zone 104.5-107.5) is touched,
    # left and touched again, so it dies; the MSS then enters on the rank 2 OB alone.
    ones, _ = day_rows()
    strategy = v2()
    run(ones, strategy=strategy)
    (low_ob,) = strategy._book.active
    swept = SwingLevel(109.0, DAY1, "low")
    high_ob = OrderBlock("bullish", 100.0, 115.0, SWEEP_LOW, low_ob.formed_at, 2, swept)
    strategy._book.add(high_ob)

    results = run(minutes(EARLY, TOUCH + [LEAVE, RETURN, MSS_1M]), strategy=strategy)

    assert not low_ob.active
    assert high_ob.rank > low_ob.rank
    plans = entries(results)
    assert len(plans) == 1 and plans[0].ob is high_ob


# TDOB v3 (TD-25 to TD-28): the sweep takes the previous candle, and the next counted candle leaves a gap.
def v3() -> TopDownOBStrategy:
    return TopDownOBStrategy(any_hour=True, skip_inside=True, first_touch_only=True, strict_ob=True)


def test_v3_ob_is_not_tradeable_until_the_next_candle_closes() -> None:
    ones, _ = day_rows()
    engulf_applied = [c for c in ones if c.open_time <= DAY2 + 31 * M15]  # first 1m after the engulfing candle closes
    next_applied = [c for c in ones if DAY2 + 31 * M15 < c.open_time <= DAY2 + 32 * M15]
    strategy = v3()

    run(engulf_applied, strategy=strategy)
    assert strategy._book._active == []

    run(next_applied, strategy=strategy)
    (ob,) = strategy._book._active
    assert (ob.zone_low, ob.zone_high) == ZONE


def test_v3_plan_when_sweep_and_gap_hold() -> None:
    candles, _ = long_scenario()

    plans = entries(run(candles, strategy=v3()))

    assert len(plans) == 1 and (plans[0].ob.zone_low, plans[0].ob.zone_high) == ZONE


def test_v3_short_plan_mirrors_the_long() -> None:
    candles, _ = long_scenario()

    plans = entries(run(mirror(candles), strategy=v3()))

    assert len(plans) == 1 and plans[0].side == "short"
    assert (plans[0].ob.zone_low, plans[0].ob.zone_high) == (MIRROR - ZONE[1], MIRROR - ZONE[0])


def test_v3_next_candle_into_the_zone_drops_the_ob_for_good() -> None:
    wick_into_zone: Row = (108, 108.6, 107.4, 108.3)  # low under the zone top 107.5
    ones, _ = day_rows(setup=SETUP[:4] + [wick_into_zone, SETUP[5]])
    strategy = v3()

    results = run(ones + minutes(NY_AM, DESCENT + [MSS]), strategy=strategy)

    assert entries(results) == []
    assert strategy._book._active == []


def test_v3_rejects_a_level_the_previous_candle_broke_itself() -> None:
    # The last decline candle (low 105.2) closes under the swing low 105.7, which records 105.7 at that close. The
    # sweep only reaches 105.4, under 105.7 but above the previous candle's low: price already went further.
    setup: list[Row] = [(105.5, 106.2, 105.4, 106.0), (106.0, 108.2, 105.9, 108.0), SETUP[4], SETUP[5]]
    ones, _ = day_rows(setup=setup)
    v2_reading = TopDownOBStrategy()
    strict = TopDownOBStrategy(strict_ob=True)

    run(ones, strategy=v2_reading)
    run(ones, strategy=strict)

    (ob,) = v2_reading._book._active
    assert ob.swept.price == 105.7
    assert strict._book._active == []


def test_v3_inside_candle_before_the_next_candle_does_not_spend_the_first_touch() -> None:
    # The inside candle wicks into the zone and closes back out. Were the OB active, that would be its first touch
    # and the later descent its second touch, which kills it.
    inside: Row = (107.0, 108.0, 106.5, 107.6)
    ones, _ = day_rows(setup=SETUP[:4] + [inside] + SETUP[4:])

    plans = entries(run(ones + minutes(NY_AM, DESCENT + [MSS]), strategy=v3()))

    assert len(plans) == 1


def test_v3_inside_close_through_the_far_side_kills_the_pending_ob() -> None:
    engulf: Row = (106.0, 108.2, 104.0, 108.0)  # a low under the sweep's, so an inside candle can close below the zone
    close_through: Row = (107.0, 108.0, 104.1, 104.2)
    ones, _ = day_rows(setup=SETUP[:3] + [engulf, close_through] + SETUP[4:])
    strategy = v3()

    run(ones, strategy=strategy)

    assert strategy._book._active == []


def test_v3_bias_flip_kills_the_pending_ob() -> None:
    # The engulfing candle closes at 23:30, then an inside candle ends the day at 108, under the daily protected low
    # 109: bearish. The gap candle comes after midnight.
    blocks = [
        (DAY0, DAY0_ROWS), (DAY1, DAY1_ROWS), (DAY2, DECLINE + SETUP[:3]),
        (DAY2 + timedelta(hours=23, minutes=30), [SETUP[3], (107.0, 108.1, 106.5, 108.0)]),
        (DAY3, [SETUP[4], SETUP[5]]),
    ]
    strategy = TopDownOBStrategy(skip_inside=True, strict_ob=True)

    run([c for start, rows in blocks for c in expand_15m(start, rows)], strategy=strategy)

    assert strategy._daily.trend == "bearish"
    assert not [ob for ob in strategy._book._active if ob.direction == "bullish"]

