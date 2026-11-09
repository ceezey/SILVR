from dataclasses import replace
from datetime import UTC, datetime, timedelta

from silvr.models import Candle
from silvr.strategy.top_down import StructureEvent, StructureTracker

START = datetime(2026, 1, 1, tzinfo=UTC)
DAY = timedelta(days=1)


def candle(i: int, high: float, low: float, close: float) -> Candle:
    open_time = START + i * DAY
    return Candle("BTCUSDT", "1d", open_time, close, high, low, close, 1.0, open_time + DAY - timedelta(milliseconds=1))


def feed(tracker: StructureTracker, rows: list[tuple[float, float, float]], start: int = 0) -> list[StructureEvent | None]:
    return [tracker.update(candle(start + i, *row)) for i, row in enumerate(rows)]


# (high, low, close). Up-leg, pullback to L=10, BoS above 12, then a close below L.
UP_LEG = [
    (10, 9, 9.5),  # seed: swing high 10, swing low 9
    (12, 11, 11.5),  # closes above 10: first break, so ChoCh; swing high restarts at 12
    (11.5, 10, 10.5),  # pullback, low 10 is the extreme
    (11, 10.2, 10.8),
    (13, 10.5, 12.5),  # closes above 12: BoS; protected low = lowest low since the 12 high = 10
]


def test_wick_through_swing_high_does_not_break() -> None:
    tracker = StructureTracker("1d")
    events = feed(tracker, [(10, 5, 8), (12, 6, 9)])  # high 12 > 10 but close 9 < 10

    assert events == [None, None]
    assert tracker.trend == "none"
    assert tracker.bullish_trigger == 12  # the wick still raises the swing high


def test_body_close_above_swing_high_is_choch_from_none_then_bos() -> None:
    tracker = StructureTracker("1d")
    events = feed(tracker, UP_LEG)

    assert events[1] == StructureEvent("choch", "bullish", 10, candle(1, 12, 11, 11.5).close_time)
    assert events[2:4] == [None, None]
    assert events[4] == StructureEvent("bos", "bullish", 12, candle(4, 13, 10.5, 12.5).close_time)
    assert tracker.trend == "bullish"


def test_protected_low_is_pullback_extreme_before_bos() -> None:
    tracker = StructureTracker("1d")
    feed(tracker, UP_LEG)

    assert tracker.bearish_trigger == 10
    assert tracker.bullish_trigger == 13


def test_close_below_protected_low_is_bearish_choch() -> None:
    tracker = StructureTracker("1d")
    feed(tracker, UP_LEG)

    event = tracker.update(candle(5, 10.5, 9.5, 9.8))

    assert event == StructureEvent("choch", "bearish", 10, candle(5, 10.5, 9.5, 9.8).close_time)
    assert tracker.trend == "bearish"
    assert tracker.bullish_trigger == 13  # protected high = highest high since the broken low's candle
    assert tracker.bearish_trigger == 9.5  # swing low restarts from the breaking candle


def test_level_marked_taken_by_wick() -> None:
    tracker = StructureTracker("1d")
    feed(tracker, UP_LEG)
    protected = next(level for level in tracker.untaken_levels("low") if level.price == 10)

    assert protected.time == candle(4, 13, 10.5, 12.5).close_time  # when it became known, not the extreme candle
    assert not protected.taken

    assert tracker.update(candle(5, 12, 9.9, 11)) is None  # wick below 10, close above: no break

    assert protected.taken
    assert protected not in tracker.untaken_levels("low")
    assert [level.price for level in tracker.untaken_levels("low")] == [9]  # the earlier protected low, newest first


def test_level_recorded_on_an_update_is_checked_from_the_next_update() -> None:
    tracker = StructureTracker("1d")
    feed(tracker, UP_LEG)

    # The BoS candle (high 13) traded through the broken 12 high, but a level recorded on an update
    # is only checked from the next update on.
    assert [level.price for level in tracker.untaken_levels("high")] == [12]
    assert [level.price for level in tracker.untaken_levels("low")][0] == 10

    tracker.update(candle(5, 11, 10.6, 10.8))  # high 11 does not reach 12
    assert [level.price for level in tracker.untaken_levels("high")] == [12]

    tracker.update(candle(6, 12, 10.6, 11))  # high 12 does

    assert tracker.untaken_levels("high") == []


def test_snapshot_copy_does_not_follow_later_taking() -> None:
    tracker = StructureTracker("1d")
    feed(tracker, UP_LEG)
    snapshot = [replace(level) for level in tracker.untaken_levels("low")]

    tracker.update(candle(5, 12, 9.9, 11))

    assert not any(level.taken for level in snapshot)


# (high, low, close): the owner's 2024-2026 daily chart in miniature.
OWNER_DAILY = [
    (100, 90, 95),  # seed
    (105, 96, 104),  # close > 100: ChoCh up
    (103, 98, 100),
    (110, 100, 109),  # close > 105: BoS, protected low 96
    (108, 102, 104),
    (107, 101, 103),
    (120, 104, 118),  # close > 110: BoS, protected low 100
    (117, 108, 110),
    (112, 98, 99),  # close < 100: ChoCh down
]


def test_owner_daily_example() -> None:
    tracker = StructureTracker("1d")
    events = [e for e in feed(tracker, OWNER_DAILY) if e is not None]

    assert [(e.kind, e.direction) for e in events] == [
        ("choch", "bullish"),
        ("bos", "bullish"),
        ("bos", "bullish"),
        ("choch", "bearish"),
    ]
    assert [e.level for e in events] == [100, 105, 110, 100]
    assert tracker.trend == "bearish"
    assert tracker.bullish_trigger == 120  # protected high: highest high since the protected low's candle


def test_choch_back_to_bullish_uses_protected_high_setter_range() -> None:
    tracker = StructureTracker("1d")
    feed(tracker, OWNER_DAILY)

    assert tracker.update(candle(9, 100, 97, 98)) is None  # close 98 is not below the swing low 98
    event = tracker.update(candle(10, 125, 99, 124))  # close above the protected high 120

    assert event == StructureEvent("choch", "bullish", 120, candle(10, 125, 99, 124).close_time)
    assert tracker.bearish_trigger == 97  # lowest low since the candle that set the 120 high
    assert tracker.bullish_trigger == 125


def test_wick_without_close_and_close_equal_to_trigger_do_not_break() -> None:
    tracker = StructureTracker("1d")
    feed(tracker, UP_LEG)

    assert tracker.update(candle(5, 13.5, 11, 13)) is None  # close equals the bullish trigger 13
    assert tracker.update(candle(6, 12, 10, 10)) is None  # close equals the protected low 10
    assert tracker.trend == "bullish"


def test_bearish_choch_from_none_then_bos() -> None:
    tracker = StructureTracker("1d")
    events = feed(tracker, [(10, 9, 9.5), (9.2, 7, 8), (9, 7.5, 8.5), (8.6, 5, 6)])

    assert [(e.kind, e.direction, e.level) for e in events[1:] if e] == [("choch", "bearish", 9), ("bos", "bearish", 7)]
    assert tracker.bullish_trigger == 9.2  # protected high: highest high since the 7 low's candle
    assert tracker.bearish_trigger == 5


def test_untaken_levels_after_long_one_way_trend() -> None:
    tracker = StructureTracker("1d")
    rows = [(11 + 2 * k, 10 + 2 * k, 11 + 2 * k) for k in range(40)]  # every close breaks the last high
    feed(tracker, rows)
    lows = tracker.untaken_levels("low")
    prices = [level.price for level in lows]

    # Price never came back down: every protected low is untaken, newest (highest) first.
    assert prices == list(range(86, 8, -2))
    assert [level.price for level in tracker.untaken_levels("high")] == [87]  # only the last broken high is unchecked

    # A wick back down to 48 takes every low at or above it, highest first, and nothing else.
    assert tracker.update(candle(40, 88, 48, 87)) is None
    survivors = tracker.untaken_levels("low")

    assert [level.price for level in survivors] == list(range(46, 8, -2))
    assert {level.price for level in lows if level.taken} == set(range(48, 87, 2))
    assert not any(level.taken for level in survivors)
    assert tracker.untaken_levels("high") == []


def test_last_taken_and_untaken_reached_by() -> None:
    tracker = StructureTracker("1d")
    feed(tracker, [(11 + 2 * k, 10 + 2 * k, 11 + 2 * k) for k in range(40)])  # untaken lows 86, 84, ..., 10
    reached = tracker.untaken_reached_by("low", 48)

    assert sorted(level.price for level in reached) == list(range(48, 87, 2))
    assert not any(level.taken for level in reached)
    assert tracker.untaken_reached_by("low", 87) == []
    assert [level.price for level in tracker.untaken_reached_by("high", 87)] == [87]

    tracker.update(candle(40, 88, 48, 87))

    assert sorted(level.price for level in tracker.last_taken) == [*range(48, 87, 2), 87]  # the 88 high takes 87
    assert all(level.taken for level in tracker.last_taken)
    tracker.update(candle(41, 88, 87, 87.5))
    assert tracker.last_taken == []  # reset by every update


def test_mark_taken_takes_levels_without_touching_structure() -> None:
    tracker = StructureTracker("1d")
    feed(tracker, UP_LEG)  # untaken: highs [12], lows [10, 9]; triggers 13 / 10
    swings = (tracker.trend, tracker.bullish_trigger, tracker.bearish_trigger)

    tracker.mark_taken(13.5, 9.95)  # above the bullish trigger 13 and below the protected low 10, but no close

    assert sorted(level.price for level in tracker.last_taken) == [10, 12]
    assert all(level.taken for level in tracker.last_taken)
    assert tracker.untaken_levels("high") == []
    assert [level.price for level in tracker.untaken_levels("low")] == [9]
    assert (tracker.trend, tracker.bullish_trigger, tracker.bearish_trigger) == swings  # a mark never breaks or folds in
    tracker.mark_taken(14, 9.5)
    assert tracker.last_taken == []  # reset by every mark; 9 is not reached

    # The next update sees the same structure it would have seen without the marks.
    unmarked = StructureTracker("1d")
    feed(unmarked, UP_LEG)
    assert tracker.update(candle(5, 10.5, 9.5, 9.8)) == unmarked.update(candle(5, 10.5, 9.5, 9.8))


def test_mark_only_reaches_levels_recorded_before_it() -> None:
    tracker = StructureTracker("1d")
    feed(tracker, UP_LEG[:4])
    breaking = candle(4, 13, 10.5, 12.5)  # the BoS candle: it records the broken high 12 (and the protected low 10)

    tracker.mark_taken(breaking.high, breaking.low)  # a candle that ended at or before the recording: 12 is not there yet
    assert tracker.last_taken == []
    tracker.update(breaking)
    assert [level.price for level in tracker.untaken_levels("high")] == [12]

    tracker.mark_taken(12.2, 10.5)  # a later candle trading through 12 takes it; 10.5 stays above the low 10

    assert [level.price for level in tracker.last_taken] == [12]
    assert tracker.untaken_levels("high") == []


def test_inside_candles_never_move_swings_or_break() -> None:
    inside = [(11.5, 9.95, 11), (11, 10.2, 10.5), (11.5, 9.95, 9.95)]  # all within the reference (12, 9.9); the last closes below the protected low 10
    results = {}
    for skip in (True, False):
        tracker = StructureTracker("1d", skip_inside=skip)
        feed(tracker, UP_LEG)
        tracker.update(candle(5, 12, 9.9, 11))  # wick below 10, close above: counts and becomes the reference
        before = (tracker.bullish_trigger, tracker.bearish_trigger, tracker.trend)
        events, counted = [], []
        for i, row in enumerate(inside):
            events.append(tracker.update(candle(6 + i, *row)))
            counted.append(tracker.last_counted)
        results[skip] = (before, events, counted, (tracker.bullish_trigger, tracker.bearish_trigger, tracker.trend))

    before, events, counted, after = results[True]
    assert before == (13, 10, "bullish")
    assert events == [None, None, None]
    assert counted == [False, False, False]
    assert after == before

    _, events, counted, _ = results[False]  # control: the same candles count by default and the last one breaks
    assert events[2] == StructureEvent("choch", "bearish", 10, candle(8, 11.5, 9.95, 9.95).close_time)
    assert counted == [True, True, True]


def test_wick_outside_reference_counts_and_becomes_reference() -> None:
    tracker = StructureTracker("1d", skip_inside=True)
    feed(tracker, UP_LEG)  # reference (13, 10.5)

    assert tracker.update(candle(5, 13.5, 11, 12.8)) is None  # only the high pokes out; no close beyond 13
    assert tracker.last_counted
    assert tracker.bullish_trigger == 13.5  # the swing high moved

    assert tracker.update(candle(6, 13.4, 11.5, 13)) is None  # outside (13, 10.5) but inside the new reference (13.5, 11)
    assert not tracker.last_counted
    assert tracker.bullish_trigger == 13.5


def test_inside_candle_takes_no_level() -> None:
    inside = candle(5, 12.5, 10.6, 11)  # within (13, 10.5) and reaches the untaken high 12
    control = StructureTracker("1d")
    feed(control, UP_LEG)
    control.update(inside)
    assert [level.price for level in control.last_taken] == [12]

    tracker = StructureTracker("1d", skip_inside=True)
    feed(tracker, UP_LEG)
    tracker.update(inside)

    assert not tracker.last_counted
    assert tracker.last_taken == []
    assert [level.price for level in tracker.untaken_levels("high")] == [12]


def test_inside_test_is_inclusive_on_both_sides() -> None:
    # Reference after UP_LEG is (13, 10.5). A candle equal to it on one or both sides is inside (high <=, low >=).
    for high, low in ((13, 10.5), (13, 11), (12, 10.5)):
        tracker = StructureTracker("1d", skip_inside=True)
        feed(tracker, UP_LEG)
        before = (tracker.bullish_trigger, tracker.bearish_trigger, tracker.trend, tracker.untaken_levels("high"))

        assert tracker.update(candle(5, high, low, 11.5)) is None
        assert not tracker.last_counted
        assert tracker.last_taken == []
        assert (tracker.bullish_trigger, tracker.bearish_trigger, tracker.trend, tracker.untaken_levels("high")) == before

        # The reference did not move: a candle inside (13, 10.5) but outside (high, low) is still skipped.
        assert tracker.update(candle(6, 12.9, 10.6, 11.5)) is None
        assert not tracker.last_counted
