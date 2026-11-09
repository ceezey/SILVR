from datetime import UTC, datetime, timedelta

import pytest

from silvr.models import Candle
from silvr.strategy.models import FairValueGap, FairValueGapDirection
from silvr.strategy.top_down import SwingLevel, atr, final_target, stage2_level, unfilled_fvgs

START = datetime(2026, 1, 1, tzinfo=UTC)
M15 = timedelta(minutes=15)
LEVEL_TIME = START - timedelta(hours=8)


def candle(i: int, open_: float, high: float, low: float, close: float) -> Candle:
    open_time = START + i * M15
    return Candle("BTCUSDT", "15m", open_time, open_, high, low, close, 1.0, open_time + M15 - timedelta(milliseconds=1))


def gap(direction: FairValueGapDirection, lower: float, upper: float) -> FairValueGap:
    return FairValueGap(direction, 2, lower, upper, (lower + upper) / 2, upper - lower, START)


def high_level(price: float, taken: bool = False) -> SwingLevel:
    return SwingLevel(price, LEVEL_TIME, "high", taken)


def low_level(price: float, taken: bool = False) -> SwingLevel:
    return SwingLevel(price, LEVEL_TIME, "low", taken)


BEARISH = FairValueGapDirection.BEARISH
BULLISH = FairValueGapDirection.BULLISH


def test_atr_of_known_series():
    candles = [
        candle(0, 10, 11, 9, 10),
        candle(1, 10, 12, 10, 11),  # TR = max(2, 2, 0) = 2
        candle(2, 11, 11.5, 10, 11),  # TR = max(1.5, 0.5, 1) = 1.5
        candle(3, 11, 16, 11, 15),  # TR = max(5, 5, 0) = 5
    ]
    assert atr(candles, period=3) == pytest.approx((2 + 1.5 + 5) / 3)
    assert atr(candles, period=2) == pytest.approx((1.5 + 5) / 2)  # only the last two TRs
    with pytest.raises(ValueError):
        atr(candles, period=4)


def test_partial_fill_still_unfilled_full_fill_removed():
    # Bearish gap 100-102 formed by candle 2 (first.low 102 > third.high 100).
    base = [candle(0, 103, 104, 102, 103), candle(1, 102, 102.5, 100.5, 101), candle(2, 100, 100, 99, 99.5)]
    partial = [*base, candle(3, 100, 101.5, 99.5, 100)]  # high 101.5 < 102: partial
    full = [*base, candle(3, 100, 102, 99.5, 100)]  # high 102 >= upper bound: filled
    (kept,) = unfilled_fvgs(partial, direction=BEARISH)
    assert (kept.lower_bound, kept.upper_bound) == (100, 102)
    assert unfilled_fvgs(full, direction=BEARISH) == []
    assert unfilled_fvgs(partial, direction=BULLISH) == []


def test_unfilled_fvgs_newest_first_and_bullish_fill():
    candles = [
        candle(0, 100, 101, 99, 100),
        candle(1, 101, 104, 101, 104),
        candle(2, 104, 106, 103, 105),  # bullish gap 101-103
        candle(3, 105, 109, 104, 108),
        candle(4, 108, 110, 108, 110),  # bullish gap 106-108
        candle(5, 110, 111, 107, 110),  # low 107 enters the 106-108 gap without closing it
    ]
    gaps = unfilled_fvgs(candles, direction=BULLISH)
    assert [(g.lower_bound, g.upper_bound) for g in gaps] == [(106, 108), (101, 103)]
    filled = [*candles, candle(6, 110, 110, 100, 101)]  # low 100 <= both lower bounds
    assert unfilled_fvgs(filled, direction=BULLISH) == []


def test_final_target_owner_example():
    fvgs = [gap(BEARISH, 84_500, 85_100)]
    levels = [high_level(86_530), high_level(87_000, taken=True), low_level(85_500)]
    assert final_target(side="long", entry=80_700, fvgs=fvgs, levels_15m=levels, cap=87_378) == 86_530


def test_final_target_picks_nearest_fvg_and_lowest_level_beyond_it():
    fvgs = [gap(BEARISH, 90_000, 90_500), gap(BEARISH, 84_500, 85_100), gap(BULLISH, 82_000, 82_500)]
    levels = [high_level(84_800), high_level(88_000), high_level(86_530), high_level(95_000)]
    assert final_target(side="long", entry=80_700, fvgs=fvgs, levels_15m=levels, cap=90_000) == 86_530


def test_final_target_falls_back_to_cap_without_fvg():
    fvgs = [gap(BEARISH, 79_000, 79_500), gap(BULLISH, 84_000, 85_000)]  # wrong side / wrong direction
    assert final_target(side="long", entry=80_700, fvgs=fvgs, levels_15m=[high_level(86_000)], cap=87_378) == 87_378


def test_final_target_cap_when_no_level_beyond_fvg():
    fvgs = [gap(BEARISH, 84_500, 85_100)]
    levels = [high_level(85_000), high_level(88_000), high_level(86_000, taken=True)]  # inside, above cap, taken
    assert final_target(side="long", entry=80_700, fvgs=fvgs, levels_15m=levels, cap=87_378) == 87_378


def test_stage2_nearest_level_at_least_1r():
    levels = [high_level(101), high_level(103), high_level(106)]
    assert stage2_level(side="long", entry=100, stop=98, final=110, levels_15m=levels) == 103


def test_stage2_none_when_no_level():
    assert stage2_level(side="long", entry=100, stop=98, final=110, levels_15m=[high_level(101)]) is None
    # a level at or beyond final does not count, nor does a taken one
    levels = [high_level(110), high_level(103, taken=True), low_level(104)]
    assert stage2_level(side="long", entry=100, stop=98, final=110, levels_15m=levels) is None


def test_short_mirror():
    fvgs = [gap(BULLISH, 14_900, 15_500), gap(BEARISH, 17_000, 18_000)]
    levels = [low_level(13_000), low_level(14_000), low_level(12_000), high_level(13_500)]
    assert final_target(side="short", entry=19_300, fvgs=fvgs, levels_15m=levels, cap=12_500) == 14_000
    assert final_target(side="short", entry=19_300, fvgs=fvgs, levels_15m=[low_level(14_900)], cap=12_500) == 12_500
    s2 = [low_level(99), low_level(97), low_level(95)]
    assert stage2_level(side="short", entry=100, stop=102, final=90, levels_15m=s2) == 97  # 99 is under 1R away
