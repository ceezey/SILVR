from datetime import UTC, datetime, timedelta

from silver_bot.models import Candle
from silver_bot.strategy import (
    BiasDirection,
    FairValueGapDirection,
    LiquidityLevel,
    LiquiditySide,
    SweepDirection,
    detect_displacement,
    detect_fair_value_gaps,
    detect_liquidity_sweep,
    detect_market_structure_shift,
    detect_swing_points,
    determine_higher_timeframe_bias,
    latest_unmitigated_fvg,
    liquidity_levels_from_swings,
)


def candle(index: int, open_: float, high: float, low: float, close: float) -> Candle:
    opened = datetime(2026, 1, 2, 15, 0, tzinfo=UTC) + timedelta(minutes=index)
    return Candle(
        symbol="BTCUSDT",
        timeframe="1m",
        open_time=opened,
        close_time=opened + timedelta(minutes=1),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1000,
    )


def test_swing_liquidity_sweep_and_market_structure_shift_detection() -> None:
    candles = [
        candle(0, 110, 115, 109, 112),
        candle(1, 112, 118, 111, 116),
        candle(2, 116, 140, 114, 119),
        candle(3, 119, 120, 105, 107),
        candle(4, 107, 108, 99, 101),
        candle(5, 101, 102, 98, 100),
        candle(6, 100, 115, 99.5, 113),
        candle(7, 113, 145, 110, 142),
    ]

    swings = detect_swing_points(candles, lookback=2)
    levels = liquidity_levels_from_swings(swings, current_index=len(candles) - 1)
    sweep = detect_liquidity_sweep(candles, levels=levels, candle_index=5)
    assert sweep is not None
    assert sweep.direction == SweepDirection.BULLISH

    mss = detect_market_structure_shift(candles, sweep=sweep, swings=swings)
    assert mss is not None
    assert mss.broken_level == 115


def test_fair_value_gap_and_displacement_detection() -> None:
    candles = [
        candle(0, 110, 115, 109, 112),
        candle(1, 112, 118, 111, 116),
        candle(2, 116, 120, 114, 119),
        candle(3, 119, 120, 105, 107),
        candle(4, 107, 108, 99, 101),
        candle(5, 101, 102, 98, 100),
        candle(6, 100, 115, 99.5, 113),
        candle(7, 113, 145, 110, 142),
    ]

    gaps = detect_fair_value_gaps(candles)
    bullish_gaps = [gap for gap in gaps if gap.direction == FairValueGapDirection.BULLISH]
    assert bullish_gaps[-1].lower_bound == 102
    assert bullish_gaps[-1].upper_bound == 110

    displacement = detect_displacement(candles[:7], direction=FairValueGapDirection.BULLISH)
    assert displacement is not None
    assert displacement.strength_score > 0


def test_fvg_detection_waits_for_confirming_third_candle() -> None:
    candles = [
        candle(0, 100, 101, 99, 100),
        candle(1, 100, 103, 100, 102),
        candle(2, 104, 106, 104, 105),
    ]

    assert detect_fair_value_gaps(candles[:2]) == []
    gaps = detect_fair_value_gaps(candles)
    assert len(gaps) == 1
    assert gaps[0].candle_index == 2


def test_fvg_retracement_only_counts_first_touch() -> None:
    candles = [
        candle(0, 100, 102, 99, 101),
        candle(1, 101, 104, 100, 103),
        candle(2, 108, 110, 108, 109),
        candle(3, 107, 109, 103, 105),
        candle(4, 106, 108, 103, 107),
    ]

    assert latest_unmitigated_fvg(
        candles[:4],
        direction=FairValueGapDirection.BULLISH,
    ) is not None
    assert latest_unmitigated_fvg(
        candles,
        direction=FairValueGapDirection.BULLISH,
    ) is None


def test_liquidity_sweep_ignores_levels_not_known_before_sweep() -> None:
    candles = [
        candle(0, 100, 105, 95, 100),
        candle(1, 100, 101, 96, 97),
        candle(2, 97, 98, 90, 96),
    ]
    future_level = LiquidityLevel(
        price=95,
        side=LiquiditySide.SELL_SIDE,
        source="future_swing_low",
        candle_index=3,
        timestamp=candles[-1].open_time + timedelta(minutes=1),
    )

    assert detect_liquidity_sweep(candles, levels=[future_level], candle_index=2) is None


def test_market_structure_shift_does_not_use_future_break_candle() -> None:
    candles = [
        candle(0, 110, 115, 109, 112),
        candle(1, 112, 118, 111, 116),
        candle(2, 116, 140, 114, 119),
        candle(3, 119, 120, 105, 107),
        candle(4, 107, 108, 99, 101),
        candle(5, 101, 102, 98, 100),
        candle(6, 100, 115, 99.5, 113),
        candle(7, 113, 145, 110, 142),
    ]
    swings = detect_swing_points(candles, lookback=2)
    levels = liquidity_levels_from_swings(swings, current_index=6)
    sweep = detect_liquidity_sweep(candles, levels=levels, candle_index=5)
    assert sweep is not None

    assert detect_market_structure_shift(candles[:7], sweep=sweep, swings=swings) is None
    assert detect_market_structure_shift(candles, sweep=sweep, swings=swings) is not None


def test_higher_timeframe_bias_detection() -> None:
    bullish = [
        candle(0, 100, 105, 95, 101),
        candle(1, 101, 106, 96, 103),
        candle(2, 103, 108, 98, 105),
        candle(3, 105, 110, 100, 108),
        candle(4, 108, 112, 102, 111),
    ]
    assert determine_higher_timeframe_bias(bullish) == BiasDirection.BULLISH
