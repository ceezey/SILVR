"""TD-29 to TD-35 of the v4 spec on hand-made candles and on the owner's trade of 30 Oct 2026 (Binance spot)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from silver_bot.data.csv_loader import load_binance_kline_csv
from silver_bot.models import Candle
from silver_bot.strategy.top_down.order_blocks import OrderBlock
from silver_bot.strategy.top_down.retest import RetestSetup, SwingTracker
from silver_bot.strategy.top_down.structure import StructureTracker, SwingLevel

START = datetime(2026, 1, 1, tzinfo=UTC)
FIXTURE = Path(__file__).parent / "fixtures" / "btcusdt_spot_1m_2026-10-30.csv"


def bar(minute: int, high: float, low: float, close: float, o: float | None = None) -> Candle:
    opened = START + timedelta(minutes=minute)
    return Candle("BTCUSDT", "1m", opened, close if o is None else o, high, low, close, 1.0, opened + timedelta(minutes=1))


def block(direction: str = "bullish", low: float = 90.0, high: float = 110.0) -> OrderBlock:
    extreme = low if direction == "bullish" else high
    side = "low" if direction == "bullish" else "high"
    return OrderBlock(direction, low, high, extreme, START, 1, SwingLevel(extreme, START, side))


def flip(candle: Candle) -> Candle:
    """The same candle reflected around 200, so a long's rule run on it must act as the short's rule."""
    return Candle(candle.symbol, candle.timeframe, candle.open_time, 200 - candle.open, 200 - candle.low,
                  200 - candle.high, 200 - candle.close, 1.0, candle.close_time)


def test_without_an_earlier_swing_the_touch_candle_high_is_the_level() -> None:
    setup = RetestSetup(block(), bar(0, 108, 104, 105), swing_high=None, swing_low=None)
    assert setup.level == 108
    setup.update(bar(1, 112, 106, 111), counted=True)
    assert setup.entry == 108  # price never left the candle, so the box is all of it


def test_swing_floor_holds_the_level_until_a_real_close_above_it() -> None:
    setup = RetestSetup(block(), bar(0, 108, 104, 105), swing_high=115, swing_low=None)
    setup.update(bar(1, 112, 106, 111), counted=True)  # above the touch candle's high, under the swing
    assert setup.entry is None and setup.level == 115
    setup.update(bar(2, 118, 100, 101), counted=True)  # new lowest low: the highest high since the touch is 118
    assert setup.level == 118 and setup.entry is None


def test_level_never_falls_when_the_swing_is_above_the_highs_since_the_touch() -> None:
    setup = RetestSetup(block(), bar(0, 108, 104, 105), swing_high=115, swing_low=None)
    setup.update(bar(1, 106, 100, 101), counted=True)
    assert setup.level == 115


def test_wick_through_the_level_is_not_a_choch() -> None:
    setup = RetestSetup(block(), bar(0, 108, 100, 105), swing_high=110, swing_low=None)
    setup.update(bar(1, 112, 101, 110), counted=True)  # wick above, close equal: no break
    assert setup.entry is None
    setup.update(bar(2, 112, 102, 110.5), counted=True)
    assert setup.entry == 108


def test_new_low_cannot_be_the_choch_on_the_same_candle() -> None:
    setup = RetestSetup(block(), bar(0, 108, 104, 105), swing_high=None, swing_low=None)
    setup.update(bar(1, 120, 100, 119), counted=True)  # new low, and its own high becomes the level
    assert setup.entry is None and setup.level == 120


# The OB candle of the box tests: low 100, lower wick to the open 101, body to the close 103, upper wick to 104.
def ob_setup() -> RetestSetup:
    return RetestSetup(block(), bar(0, 104, 100, 103, o=101), swing_high=108, swing_low=None)


LEAVE = bar(1, 107, 105, 106)  # low above the OB candle's high: price has left it
CHOCH = bar(3, 110, 104.5, 109)


@pytest.mark.parametrize(
    ("touch_low", "box_top"),
    [
        (104.01, 104),  # no touch: the full candle
        (104.0, 103),  # the upper wick, at its top: body and lower wick
        (103.5, 103),
        (103.0, 101),  # the body, at its top: the lower wick alone
        (102.0, 101),
        (100.5, 101),
    ],
)
def test_box_is_a_whole_part_of_the_candle(touch_low: float, box_top: float) -> None:
    setup = ob_setup()
    for candle in (LEAVE, bar(2, 106, touch_low, 105), CHOCH):
        setup.update(candle, counted=True)
    assert setup.entry == box_top


def test_box_of_a_red_ob_candle_uses_its_open_as_the_body_top() -> None:
    setup = RetestSetup(block(), bar(0, 104, 100, 101, o=103), swing_high=108, swing_low=None)
    for candle in (LEAVE, bar(2, 106, 103.5, 105), CHOCH):
        setup.update(candle, counted=True)
    assert setup.entry == 103


def test_candles_before_price_leaves_do_not_count_as_touches() -> None:
    setup = ob_setup()
    setup.update(bar(1, 106, 100.5, 105), counted=True)  # overlaps the body, but price never left the candle
    setup.update(bar(2, 107, 104, 106), counted=True)  # low equal to the candle's high: still not left
    setup.update(bar(3, 106, 103.5, 105), counted=True)
    setup.update(CHOCH, counted=True)
    assert setup.entry == 104


def test_box_never_grows_back() -> None:
    setup = ob_setup()
    for candle in (LEAVE, bar(2, 106, 102, 105), bar(3, 106, 103.5, 105), bar(4, 110, 104.5, 109)):
        setup.update(candle, counted=True)
    assert setup.entry == 101


def test_new_low_restarts_the_box() -> None:
    setup = ob_setup()
    setup.update(LEAVE, counted=True)
    setup.update(bar(2, 106, 102, 105), counted=True)  # the body: the old box is the wick
    setup.update(bar(3, 103, 99, 102, o=100), counted=True)  # new OB candle, not yet left
    setup.update(bar(4, 110, 104, 109), counted=True)
    assert setup.entry == 103


def test_equal_low_keeps_the_earlier_ob_candle() -> None:
    setup = ob_setup()
    setup.update(bar(1, 106, 100, 105), counted=True)  # equal low, before price leaves
    setup.update(CHOCH, counted=True)
    assert setup.entry == 104


def test_inside_candles_change_nothing() -> None:
    setup = RetestSetup(block(), bar(0, 104, 100, 103), swing_high=103.5, swing_low=None)
    setup.update(bar(1, 104, 100.5, 103.9), counted=False)  # closes above the level, inside the OB candle
    assert setup.entry is None
    setup.update(bar(2, 110, 105, 109), counted=True)
    assert setup.entry == 104


def test_fill_needs_price_strictly_through_the_entry() -> None:
    setup = RetestSetup(block(), bar(0, 104, 100, 103), swing_high=108, swing_low=None)
    setup.update(bar(1, 112, 105, 111), counted=True)
    assert not setup.fills(bar(2, 112, 104, 110))  # equal: not through
    assert setup.fills(bar(3, 112, 103.99, 110))


def test_short_mirrors_the_long() -> None:
    long = ob_setup()
    short = RetestSetup(block("bearish"), flip(bar(0, 104, 100, 103, o=101)), swing_high=None, swing_low=200 - 108)
    for candle in (LEAVE, bar(2, 106, 103.5, 105), CHOCH):
        long.update(candle, counted=True)
        short.update(flip(candle), counted=True)
    assert long.entry == 103 and short.entry == 200 - 103
    assert short.level == 200 - long.level
    assert short.fills(flip(bar(4, 112, 102.9, 110))) and not short.fills(flip(bar(4, 112, 103, 110)))

def test_swing_tracker_marks_the_candle_above_both_neighbours() -> None:
    swings = SwingTracker()
    for candle in (bar(0, 100, 95, 98), bar(1, 105, 96, 100), bar(2, 104, 90, 92), bar(3, 103, 94, 100)):
        swings.update(candle)
    assert swings.high == 105 and swings.low == 90


def owner_trade() -> list[Candle]:
    return load_binance_kline_csv([FIXTURE], symbol="BTCUSDT", timeframe="1m").candles


def at(hour: int, minute: int) -> datetime:
    return datetime(2026, 10, 30, hour, minute, tzinfo=UTC)


def test_owner_trade_of_30_oct_is_reproduced() -> None:
    """The owner's chart: ChoCh about 77,300 closed at 23:00 UTC+8, entry 76,685.54 (the body top drawn by hand),
    filled before 03:00 UTC+8."""
    candles = owner_trade()
    tracker, swings = StructureTracker("1m", skip_inside=True), SwingTracker()
    setup = choch = fill = None
    for candle in candles:
        tracker.update(candle)
        counted = tracker.last_counted
        if counted:
            swings.update(candle)
        if candle.open_time < at(13, 32):
            continue
        if setup is None:
            setup = RetestSetup(block(low=76500.11, high=77091.96), candle, swings.high, swings.low)
        elif setup.entry is None:
            setup.update(candle, counted)
            if setup.entry is not None:
                choch = candle.open_time
        elif setup.fills(candle):
            fill = candle.open_time
            break

    assert setup is not None
    assert setup.level == pytest.approx(77304.01)
    assert choch == at(15, 0)
    assert setup.entry == pytest.approx(76686.94)  # the 21:52 candle's body top: price left it, then touched its wick
    assert fill == at(18, 48)
