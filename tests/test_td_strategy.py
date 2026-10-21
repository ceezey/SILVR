from datetime import UTC, datetime, timedelta

import pytest

from silver_bot.data import resample
from silver_bot.models import Candle
from silver_bot.strategy.top_down import StepResult, StructureTracker, TopDownOBStrategy, atr
from silver_bot.strategy.top_down import strategy as strategy_module

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


def day_rows(day2_close: float = 110.0, day0_rows: list[Row] = DAY0_ROWS) -> tuple[list[Candle], list[Candle]]:
    """(1m candles, intended 15m candles) for days 0 to 2. day2_close is the close of day 2's last 15m candle."""
    last = [(108.3, max(108.5, day2_close + 0.2), min(108.2, day2_close - 0.2), day2_close)]
    late = DAY2 + timedelta(hours=23, minutes=45)
    blocks = [(DAY0, day0_rows), (DAY1, DAY1_ROWS), (DAY2, DECLINE + SETUP), (late, last)]
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
