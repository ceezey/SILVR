from datetime import UTC, datetime, timedelta
from pathlib import Path

from silver_bot.backtest import BacktestConfig, BacktestEngine, ExitReason
from silver_bot.models import Candle
from silver_bot.risk import RiskConfig
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


def engine(config: BacktestConfig | None = None) -> BacktestEngine:
    return BacktestEngine(
        strategy=SilverBulletStrategyEngine(
            SilverBulletStrategyConfig(
                swing_lookback=2,
                atr_period=3,
                minimum_rr=2.0,
                minimum_signal_score=70,
            )
        ),
        config=config or BacktestConfig(maker_fee=0.0, taker_fee=0.0),
    )


def test_backtest_records_winning_trade_and_exports(tmp_path: Path) -> None:
    candles = [
        *valid_long_setup(),
        candle(9, 112, 141, 105, 140),
    ]

    result = engine(
        BacktestConfig(maker_fee=0.0, taker_fee=0.0, export_dir=tmp_path)
    ).run(candles)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == ExitReason.TAKE_PROFIT
    assert trade.entry_price == 106
    assert trade.exit_price == 140
    assert trade.position_size == 6.25
    assert trade.realized_pnl == 212.5
    assert result.metrics["total_trades"] == 1
    assert result.metrics["win_rate"] == 1.0
    assert result.metrics["net_profit"] == 212.5
    assert (tmp_path / "trades.csv").exists()
    assert (tmp_path / "equity_curve.csv").exists()
    assert (tmp_path / "backtest_report.json").exists()
    assert (tmp_path / "rejected_signals.csv").exists()


def test_backtest_records_losing_trade() -> None:
    candles = [
        *valid_long_setup(),
        candle(9, 112, 113, 97, 99),
    ]

    result = engine().run(candles)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == ExitReason.STOP_LOSS
    assert trade.entry_price == 106
    assert trade.exit_price == 98
    assert trade.position_size == 6.25
    assert trade.realized_pnl == -50
    assert result.metrics["losing_trades"] == 1
    assert result.metrics["max_consecutive_losses"] == 1


def test_backtest_records_no_trade_rejections() -> None:
    outside_session = [
        Candle(
            symbol=item.symbol,
            timeframe=item.timeframe,
            open_time=item.open_time + timedelta(hours=6),
            close_time=(item.close_time + timedelta(hours=6)) if item.close_time else None,
            open=item.open,
            high=item.high,
            low=item.low,
            close=item.close,
            volume=item.volume,
        )
        for item in valid_long_setup()
    ]

    result = engine().run(outside_session)

    assert result.trades == []
    assert result.metrics["total_trades"] == 0
    assert result.rejected_signals
    assert result.rejected_signals[-1].reason == "Outside enabled Silver Bullet session"


def test_fees_reduce_net_profit() -> None:
    candles = [
        *valid_long_setup(),
        candle(9, 112, 141, 105, 140),
    ]

    no_fee = engine(BacktestConfig(maker_fee=0.0, taker_fee=0.0)).run(candles)
    with_fee = engine(BacktestConfig(maker_fee=0.001, taker_fee=0.001)).run(candles)

    assert with_fee.trades[0].fees > 0
    assert with_fee.metrics["net_profit"] < no_fee.metrics["net_profit"]


def test_slippage_reduces_net_profit() -> None:
    candles = [
        *valid_long_setup(),
        candle(9, 112, 141, 105, 140),
    ]

    no_slippage = engine(BacktestConfig(maker_fee=0.0, taker_fee=0.0, slippage_bps=0.0)).run(candles)
    with_slippage = engine(BacktestConfig(maker_fee=0.0, taker_fee=0.0, slippage_bps=10.0)).run(candles)

    assert with_slippage.trades[0].slippage > 0
    assert with_slippage.metrics["net_profit"] < no_slippage.metrics["net_profit"]


def test_limit_order_not_filled_if_price_never_reaches_entry() -> None:
    candles = [
        *valid_long_setup(),
        candle(9, 116, 125, 116, 120),
        candle(10, 121, 130, 121, 128),
    ]

    result = engine().run(candles)

    assert result.trades == []
    assert result.metrics["total_trades"] == 0


def test_backtest_logs_risk_rejection_when_kill_switch_active(tmp_path: Path) -> None:
    kill_file = tmp_path / "KILL_SWITCH"
    kill_file.write_text("stop", encoding="utf-8")
    candles = [
        *valid_long_setup(),
        candle(9, 112, 141, 105, 140),
    ]

    result = engine(
        BacktestConfig(
            maker_fee=0.0,
            taker_fee=0.0,
            risk=RiskConfig(kill_switch_path=kill_file),
        )
    ).run(candles)

    assert result.trades == []
    assert any(record.reason == "Risk rejected: Kill switch is active" for record in result.rejected_signals)
