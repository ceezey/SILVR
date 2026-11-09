from datetime import UTC, datetime, timedelta

import pytest

from silvr.models import Candle
from silvr.strategy.top_down import OrderBlock, OrderBookOfBlocks, SwingLevel, detect_order_block
from silvr.strategy.top_down.order_blocks import leaves_gap, takes_previous_candle

START = datetime(2026, 1, 1, tzinfo=UTC)
M15 = timedelta(minutes=15)
LEVEL_TIME = START - timedelta(hours=8)  # recorded well before the sweep candle opens


def candle(i: int, open_: float, high: float, low: float, close: float, tf: str = "15m") -> Candle:
    open_time = START + i * M15
    return Candle("BTCUSDT", tf, open_time, open_, high, low, close, 1.0, open_time + M15 - timedelta(milliseconds=1))


def low_level(price: float, taken: bool = False, time: datetime = LEVEL_TIME) -> SwingLevel:
    return SwingLevel(price, time, "low", taken)


def high_level(price: float) -> SwingLevel:
    return SwingLevel(price, LEVEL_TIME, "high")


# Owner example: a 4H low at 100; sweep dips to 99 and closes back at 101; the next candle engulfs above 104.
PREV2 = candle(0, 103, 104, 101.5, 102)
SWEEP = candle(1, 102, 103, 99, 101)
ENGULF = candle(2, 101, 106, 100.5, 105)


def bullish_ob(rank_levels_4h: list[SwingLevel] | None = None, levels_15m: list[SwingLevel] | None = None) -> OrderBlock:
    ob = detect_order_block(
        PREV2, SWEEP, ENGULF, bias="bullish", levels_4h=rank_levels_4h or [], levels_15m=levels_15m or []
    )
    assert ob is not None
    return ob


def test_owner_example_bullish_ob() -> None:
    level = low_level(100)
    ob = bullish_ob([level])

    assert ob.direction == "bullish"
    assert (ob.zone_low, ob.zone_high) == (99, 104)
    assert ob.sweep_extreme == 99
    assert ob.rank == 2
    assert ob.formed_at == ENGULF.close_time
    assert ob.swept is level
    assert ob.active


def test_15m_sweep_has_rank_1() -> None:
    assert bullish_ob(levels_15m=[low_level(100)]).rank == 1


def test_wick_without_engulf_is_not_ob() -> None:
    weak = candle(2, 101, 104, 100.5, 103.5)  # bullish but closes inside the two candles' highs
    equal = candle(2, 101, 105, 100.5, 104)  # closes exactly at the high: not above it
    for engulf in (weak, equal):
        assert detect_order_block(PREV2, SWEEP, engulf, bias="bullish", levels_4h=[low_level(100)], levels_15m=[]) is None


def test_engulf_must_be_bullish() -> None:
    bearish_engulf = candle(2, 106, 106, 100.5, 105)
    assert detect_order_block(PREV2, SWEEP, bearish_engulf, bias="bullish", levels_4h=[low_level(100)], levels_15m=[]) is None


def test_engulf_without_sweep_is_not_ob() -> None:
    no_sweep = candle(1, 102, 103, 100.5, 101)  # low stays above the level
    closes_below = candle(1, 102, 103, 99, 99.5)  # sweeps but does not close back above
    for sweep in (no_sweep, closes_below):
        assert detect_order_block(PREV2, sweep, ENGULF, bias="bullish", levels_4h=[low_level(100)], levels_15m=[]) is None


def test_taken_level_does_not_count() -> None:
    assert detect_order_block(PREV2, SWEEP, ENGULF, bias="bullish", levels_4h=[low_level(100, taken=True)], levels_15m=[]) is None


def test_level_recorded_after_sweep_opened_does_not_count() -> None:
    late = low_level(100, time=SWEEP.open_time)
    assert detect_order_block(PREV2, SWEEP, ENGULF, bias="bullish", levels_4h=[late], levels_15m=[]) is None


def test_levels_of_the_other_side_are_ignored() -> None:
    assert detect_order_block(PREV2, SWEEP, ENGULF, bias="bullish", levels_4h=[high_level(100)], levels_15m=[]) is None


def test_ob_against_bias_is_none() -> None:
    for bias in ("bearish", "none"):
        assert detect_order_block(PREV2, SWEEP, ENGULF, bias=bias, levels_4h=[low_level(100)], levels_15m=[]) is None


def test_4h_level_wins_and_newest_level_breaks_ties() -> None:
    old, new = low_level(100, time=LEVEL_TIME), low_level(100.5, time=LEVEL_TIME + timedelta(hours=1))
    assert bullish_ob([old, new]).swept is new
    assert bullish_ob([new, old]).swept is new
    assert bullish_ob([low_level(99.5)], [new]).swept.price == 99.5  # 4H beats 15m even when the 15m one is newer


def test_bearish_mirror() -> None:
    prev2 = candle(0, 101, 102.5, 100, 101.5)
    sweep = candle(1, 101.5, 105, 101, 104)  # high 105 sweeps the 4H high at 104.5, closes back below
    engulf = candle(2, 104, 104.5, 98, 99)  # closes below min(100, 102) = 100
    level = SwingLevel(104.5, LEVEL_TIME, "high")

    ob = detect_order_block(prev2, sweep, engulf, bias="bearish", levels_4h=[level], levels_15m=[])
    assert ob is not None
    assert (ob.direction, ob.rank, ob.sweep_extreme) == ("bearish", 2, 105)
    assert (ob.zone_low, ob.zone_high) == (100, 105)
    assert ob.swept is level

    assert detect_order_block(prev2, sweep, engulf, bias="bullish", levels_4h=[level], levels_15m=[]) is None
    assert detect_order_block(prev2, sweep, engulf, bias="bearish", levels_4h=[], levels_15m=[low_level(104.5)]) is None
    not_engulfed = candle(2, 104, 104.5, 100.5, 101)
    assert detect_order_block(prev2, sweep, not_engulfed, bias="bearish", levels_4h=[level], levels_15m=[]) is None


def test_15m_close_below_zone_invalidates() -> None:
    book = OrderBookOfBlocks()
    ob = bullish_ob([low_level(100)])
    book.add(ob)

    book.on_15m_close(candle(3, 100, 101, 99, 99.5))  # inside the zone: still active
    assert ob.active
    book.on_15m_close(candle(4, 99.5, 100, 98, 98.5))  # closes below the zone low 99
    assert not ob.active
    assert book.best_touched(candle(5, 100, 101, 98, 100, "1m")) is None


def test_bearish_ob_invalidated_by_close_above_zone() -> None:
    book = OrderBookOfBlocks()
    ob = OrderBlock("bearish", 100, 105, 105, ENGULF.close_time, 1, SwingLevel(104.5, LEVEL_TIME, "high"))
    book.add(ob)

    book.on_15m_close(candle(3, 104, 107, 103, 105))  # close at the zone high is not beyond it
    assert ob.active
    book.on_15m_close(candle(4, 105, 108, 104, 105.5))
    assert not ob.active


def test_bias_flip_deactivates() -> None:
    book = OrderBookOfBlocks()
    bull = bullish_ob([low_level(100)])
    bear = OrderBlock("bearish", 100, 105, 105, ENGULF.close_time, 1, SwingLevel(104.5, LEVEL_TIME, "high"))
    book.add(bull)
    book.add(bear)

    book.on_bias("bullish")
    assert bull.active and not bear.active
    book.on_bias("none")
    assert not bull.active


def test_consumed_ob_not_returned() -> None:
    book = OrderBookOfBlocks()
    ob = bullish_ob([low_level(100)])
    book.add(ob)
    touch = candle(5, 100, 101, 99.5, 100, "1m")

    assert book.best_touched(touch) is ob
    book.consume(ob)
    assert not ob.active
    assert book.best_touched(touch) is None


def test_touch_needs_range_overlap() -> None:
    book = OrderBookOfBlocks()
    book.add(bullish_ob([low_level(100)]))  # zone [99, 104]

    assert book.best_touched(candle(5, 105, 106, 104.5, 105, "1m")) is None
    assert book.best_touched(candle(5, 105, 106, 104, 105, "1m")) is not None  # low touches the zone high
    assert book.best_touched(candle(5, 98, 99, 97, 98, "1m")) is not None  # high touches the zone low
    assert book.best_touched(candle(5, 98, 98.9, 97, 98, "1m")) is None


def test_4h_outranks_15m_when_both_touched() -> None:
    book = OrderBookOfBlocks()
    rank1_new = OrderBlock("bullish", 98, 104, 98, ENGULF.close_time + M15, 1, low_level(99))
    rank2_old = bullish_ob([low_level(100)])
    book.add(rank2_old)
    book.add(rank1_new)

    assert book.best_touched(candle(5, 100, 101, 99.5, 100, "1m")) is rank2_old


def test_newest_wins_at_equal_rank() -> None:
    book = OrderBookOfBlocks()
    older = OrderBlock("bullish", 98, 104, 98, ENGULF.close_time, 1, low_level(99))
    newer = OrderBlock("bullish", 98, 104, 98, ENGULF.close_time + M15, 1, low_level(99))
    book.add(newer)
    book.add(older)

    assert book.best_touched(candle(5, 100, 101, 99.5, 100, "1m")) is newer


# TD-25: the sweep trades past the candle before it; equal is not a take.
@pytest.mark.parametrize(
    ("bias", "prev2_extreme", "sweep_extreme", "expected"),
    [
        ("bullish", 101.0, 99.0, True),
        ("bullish", 99.0, 99.0, False),
        ("bullish", 98.0, 99.0, False),
        ("bearish", 101.0, 103.0, True),
        ("bearish", 103.0, 103.0, False),
        ("bearish", 104.0, 103.0, False),
    ],
)
def test_sweep_must_take_the_previous_candle(
    bias: str, prev2_extreme: float, sweep_extreme: float, expected: bool
) -> None:
    prev2 = candle(0, 100, max(prev2_extreme, 100), min(prev2_extreme, 100), 100)
    sweep = candle(1, 100, max(sweep_extreme, 100), min(sweep_extreme, 100), 100)

    assert takes_previous_candle(prev2, sweep, bias) is expected


# TD-26: the next candle stays clear of the zone 99-104; equal is no gap.
@pytest.mark.parametrize(
    ("direction", "next_high", "next_low", "expected"),
    [
        ("bullish", 108.0, 104.5, True),
        ("bullish", 108.0, 104.0, False),
        ("bullish", 108.0, 103.0, False),
        ("bearish", 98.5, 95.0, True),
        ("bearish", 99.0, 95.0, False),
        ("bearish", 100.0, 95.0, False),
    ],
)
def test_next_candle_must_leave_a_gap(direction: str, next_high: float, next_low: float, expected: bool) -> None:
    ob = OrderBlock(direction, 99.0, 104.0, 99.0, START, 1, low_level(100))

    assert leaves_gap(ob, candle(3, next_low, next_high, next_low, next_high)) is expected
