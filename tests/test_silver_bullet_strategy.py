from datetime import UTC, datetime, timedelta

from silver_bot.models import Candle, SignalDirection
from silver_bot.strategy import SilverBulletStrategyConfig, SilverBulletStrategyEngine


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


def valid_long_setup() -> list[Candle]:
    return [
        candle(0, 110, 115, 109, 112),
        candle(1, 112, 118, 111, 116),
        candle(2, 116, 140, 114, 119),
        candle(3, 119, 120, 105, 107),
        candle(4, 107, 108, 99, 101),
        candle(5, 101, 102, 98, 100),
        candle(6, 100, 115, 99.5, 113),
        candle(7, 113, 145, 110, 142),
        candle(8, 112, 115, 105, 112),
    ]


def valid_short_setup() -> list[Candle]:
    return [
        candle(0, 90, 91, 85, 88),
        candle(1, 88, 89, 82, 84),
        candle(2, 84, 86, 60, 81),
        candle(3, 81, 95, 80, 93),
        candle(4, 93, 101, 92, 99),
        candle(5, 99, 102, 98, 100),
        candle(6, 100, 100.5, 85, 87),
        candle(7, 87, 90, 55, 58),
        candle(8, 94, 96, 91, 94),
    ]


def test_strategy_generates_long_signal_for_complete_silver_bullet_setup() -> None:
    engine = SilverBulletStrategyEngine(
        SilverBulletStrategyConfig(
            swing_lookback=2,
            atr_period=3,
            minimum_rr=2.0,
            minimum_signal_score=70,
        )
    )

    signal = engine.evaluate(valid_long_setup())

    assert signal.direction == SignalDirection.LONG
    assert signal.symbol == "BTCUSDT"
    assert signal.timeframe == "1m"
    assert signal.session_name == "new_york_am"
    assert signal.entry_price == 106
    assert signal.stop_loss == 98
    assert signal.take_profit == 140
    assert signal.risk_reward_ratio == 4.25
    assert signal.setup_quality_score >= 70
    assert signal.generated_at == valid_long_setup()[-1].close_time
    assert "Risk engine approval is still required" in signal.explanation


def test_strategy_generates_short_signal_for_complete_silver_bullet_setup() -> None:
    engine = SilverBulletStrategyEngine(
        SilverBulletStrategyConfig(
            swing_lookback=2,
            atr_period=3,
            minimum_rr=2.0,
            minimum_signal_score=70,
        )
    )

    signal = engine.evaluate(valid_short_setup())

    assert signal.direction == SignalDirection.SHORT
    assert signal.symbol == "BTCUSDT"
    assert signal.timeframe == "1m"
    assert signal.session_name == "new_york_am"
    assert signal.entry_price == 94
    assert signal.stop_loss == 102
    assert signal.take_profit == 60
    assert signal.risk_reward_ratio == 4.25
    assert signal.setup_quality_score >= 70
    assert "Risk engine approval is still required" in signal.explanation


def test_strategy_rejects_outside_session_with_clear_reason() -> None:
    outside_session = [
        Candle(
            symbol=item.symbol,
            timeframe=item.timeframe,
            open_time=item.open_time + timedelta(hours=6),
            open=item.open,
            high=item.high,
            low=item.low,
            close=item.close,
            volume=item.volume,
        )
        for item in valid_long_setup()
    ]
    engine = SilverBulletStrategyEngine(SilverBulletStrategyConfig(swing_lookback=2))

    signal = engine.evaluate(outside_session)

    assert signal.direction == SignalDirection.NO_TRADE
    assert signal.reason == "Outside enabled Silver Bullet session"


def test_strategy_rejects_when_latest_candle_has_not_retraced_into_fvg() -> None:
    candles = valid_long_setup()
    no_retrace = [
        *candles[:-1],
        Candle(
            symbol="BTCUSDT",
            timeframe="1m",
            open_time=candles[-1].open_time,
            close_time=candles[-1].close_time,
            open=120,
            high=125,
            low=116,
            close=122,
            volume=1000,
        ),
    ]
    engine = SilverBulletStrategyEngine(SilverBulletStrategyConfig(swing_lookback=2))

    signal = engine.evaluate(no_retrace)

    assert signal.direction == SignalDirection.NO_TRADE
    assert signal.reason == "No retracement into matching Fair Value Gap"
