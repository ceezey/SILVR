import inspect
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from silvr.backtest import BacktestConfig, BacktestEngine
from silvr.backtest.sim_kill_switch import SimulatedKillSwitch
from silvr.models import Candle, SignalDirection
from silvr.risk import KillSwitch, RiskManagementEngine
from silvr.strategy import SilverBulletStrategyEngine
from silvr.strategy.models import SilverBulletSignal

REASON = "Max consecutive losses limit reached"
SRC = Path(__file__).resolve().parents[1] / "src" / "silvr"


def test_constructor_takes_no_path() -> None:
    assert not inspect.signature(SimulatedKillSwitch).parameters

    with SimulatedKillSwitch() as ks:
        scratch = ks.path.parent
        assert scratch.is_dir()
        assert ks.path.name == "KILL_SWITCH"
        assert not ks.is_active()

    assert not scratch.exists()


def test_trip_records_simulated_time() -> None:
    at = datetime(2024, 3, 4, 15, 0, tzinfo=UTC)
    with SimulatedKillSwitch() as ks:
        ks.now = at
        ks.trip(REASON)

        assert ks.is_active()
        assert ks.trips == [{"reason": REASON, "tripped_at": at, "reset_at": None}]


def test_no_reset_same_day_reset_next_day() -> None:
    with SimulatedKillSwitch() as ks:
        ks.now = datetime(2024, 3, 4, 15, 0, tzinfo=UTC)
        ks.trip(REASON)

        assert ks.reset_if_new_day(datetime(2024, 3, 4, 23, 59, tzinfo=UTC)) is False
        assert ks.is_active()

        next_day = datetime(2024, 3, 5, 0, 0, tzinfo=UTC)
        assert ks.reset_if_new_day(next_day) is True
        assert not ks.is_active()
        assert ks.trips[0]["reset_at"] == next_day


def test_second_trip_same_day_not_reset_and_counted() -> None:
    with SimulatedKillSwitch() as ks:
        ks.now = datetime(2024, 3, 4, 15, 0, tzinfo=UTC)
        ks.trip(REASON)
        assert ks.reset_if_new_day(datetime(2024, 3, 5, 0, 0, tzinfo=UTC)) is True

        ks.now = datetime(2024, 3, 5, 10, 0, tzinfo=UTC)
        ks.trip("Max daily loss limit reached")

        assert len(ks.trips) == 2
        assert ks.reset_if_new_day(datetime(2024, 3, 5, 20, 0, tzinfo=UTC)) is False
        assert ks.is_active()


def test_trip_while_active_keeps_first_reason_and_is_not_recounted() -> None:
    with SimulatedKillSwitch() as ks:
        ks.now = datetime(2024, 3, 4, 15, 0, tzinfo=UTC)
        ks.trip(REASON)
        ks.now = datetime(2024, 3, 4, 16, 0, tzinfo=UTC)
        ks.trip("Max daily loss limit reached")

        assert len(ks.trips) == 1
        assert ks.trips[0]["reason"] == REASON


def test_trip_on_last_day_has_no_reset() -> None:
    with SimulatedKillSwitch() as ks:
        ks.now = datetime(2024, 3, 4, 15, 0, tzinfo=UTC)
        ks.trip(REASON)

        report = ks.report()

    assert report["mode"] == "simulated_per_run_daily_reset"
    assert report["trips"] == 1
    assert report["trip_log"] == [
        {"reason": REASON, "tripped_at": "2024-03-04T15:00:00+00:00", "reset_at": None}
    ]


def test_report_of_untripped_switch() -> None:
    with SimulatedKillSwitch() as ks:
        assert ks.report() == {"mode": "simulated_per_run_daily_reset", "trips": 0, "trip_log": []}


def flat_candle(opened: datetime, *, low: float = 99, high: float = 101) -> Candle:
    return Candle(
        symbol="BTCUSDT",
        timeframe="1m",
        open_time=opened,
        close_time=opened + timedelta(minutes=1),
        open=100,
        high=high,
        low=low,
        close=100,
        volume=1000,
    )


class ScriptedStrategy:
    """Returns a prepared LONG signal at chosen candle open times, else NO_TRADE."""

    # The engine reads the session clock for the pending order's expiry (session-end expiry).
    sessions = SilverBulletStrategyEngine().sessions

    def __init__(self, signal_times: set[datetime]) -> None:
        self.signal_times = signal_times

    def evaluate(self, candles):
        last = candles[-1]
        if last.open_time not in self.signal_times:
            return SilverBulletSignal(
                direction=SignalDirection.NO_TRADE,
                symbol=last.symbol,
                timeframe=last.timeframe,
                generated_at=last.open_time,
                reason="scripted: no setup",
                explanation="scripted",
            )
        return SilverBulletSignal(
            direction=SignalDirection.LONG,
            symbol=last.symbol,
            timeframe=last.timeframe,
            generated_at=last.open_time,
            reason=None,
            explanation="scripted",
            entry_price=100.0,
            stop_loss=98.0,
            take_profit=104.0,
            risk_reward_ratio=2.0,
            session_name="scripted",
            setup_quality_score=90,
        )


def three_losses_then_next_day_setup() -> tuple[list[Candle], datetime, set[datetime]]:
    """Day 1: three losing trades. Day 2: first candle carries a setup that then wins."""

    day1 = datetime(2026, 1, 2, 10, 0, tzinfo=UTC)
    day2 = datetime(2026, 1, 3, 0, 0, tzinfo=UTC)
    candles: list[Candle] = []
    for attempt in range(3):
        base = day1 + timedelta(minutes=attempt * 3)
        candles.append(flat_candle(base))  # signal candle
        candles.append(flat_candle(base + timedelta(minutes=1), low=97))  # fills, stops out
        candles.append(flat_candle(base + timedelta(minutes=2)))
    candles.append(flat_candle(day1 + timedelta(minutes=9)))  # day 1 setup, blocked by the trip
    candles.append(flat_candle(day2))  # day 2 signal candle
    candles.append(flat_candle(day2 + timedelta(minutes=1), high=105))  # fills, hits target
    signals = {candles[0].open_time, candles[3].open_time, candles[6].open_time, candles[9].open_time, day2}
    return candles, day2, signals


def run_scenario(kill_switch: KillSwitch):
    candles, day2, signals = three_losses_then_next_day_setup()
    config = BacktestConfig(maker_fee=0.0, taker_fee=0.0, slippage_bps=0.0, spread_bps=0.0)
    engine = BacktestEngine(
        strategy=ScriptedStrategy(signals),
        config=config,
        risk_engine=RiskManagementEngine(config.risk, kill_switch=kill_switch),
    )
    return engine.run(candles), day2


def test_engine_resumes_trading_next_day() -> None:
    with SimulatedKillSwitch() as ks:
        result, day2 = run_scenario(ks)

        assert [trade.realized_pnl < 0 for trade in result.trades] == [True, True, True, False]
        assert result.trades[-1].entry_time > day2
        assert len(ks.trips) == 1
        assert ks.trips[0]["reason"] == REASON
        assert ks.trips[0]["tripped_at"].date() == datetime(2026, 1, 2).date()
        assert ks.trips[0]["reset_at"] == day2
        assert any(record.reason == "Risk rejected: Kill switch is active" for record in result.rejected_signals)


def test_plain_kill_switch_never_resets(tmp_path: Path) -> None:
    ks = KillSwitch(tmp_path / "KS")

    result, day2 = run_scenario(ks)

    assert len(result.trades) == 3
    assert all(trade.entry_time < day2 for trade in result.trades)
    assert ks.path.exists()


def test_reset_hook_ignores_plain_kill_switch(tmp_path: Path) -> None:
    ks = KillSwitch(tmp_path / "KS")
    ks.trip(REASON)

    result, _ = run_scenario(ks)

    assert result.trades == []
    assert ks.path.exists()


def test_risk_and_execution_packages_do_not_import_sim_kill_switch() -> None:
    files = [
        *(SRC / "risk").rglob("*.py"),
        *(SRC / "execution").rglob("*.py"),
        *(SRC / "exchange").rglob("*.py"),
        SRC / "main.py",
        SRC / "__main__.py",
        SRC / "readiness.py",
        SRC / "demo_readiness.py",
    ]
    assert len(files) > 4
    assert all(path.is_file() for path in files)
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "sim_kill_switch" not in text, path
        assert "reset_if_new_day" not in text, path


def test_not_entered_fails_closed() -> None:
    ks = SimulatedKillSwitch()

    assert ks.is_active()
    with pytest.raises(RuntimeError, match="outside its with-block"):
        ks.trip(REASON)
    with pytest.raises(RuntimeError, match="outside its with-block"):
        ks.reset_if_new_day(datetime(2024, 3, 5, tzinfo=UTC))
    assert ks.trips == []


def test_after_exit_fails_closed() -> None:
    with SimulatedKillSwitch() as ks:
        assert not ks.is_active()

    assert ks.is_active()
    with pytest.raises(RuntimeError, match="outside its with-block"):
        ks.trip(REASON)
    with pytest.raises(RuntimeError, match="outside its with-block"):
        ks.reset_if_new_day(datetime(2024, 3, 5, tzinfo=UTC))


def test_double_enter_raises_without_leaking_scratch() -> None:
    with SimulatedKillSwitch() as ks:
        scratch = ks.path.parent
        with pytest.raises(RuntimeError, match="already entered"):
            ks.__enter__()
        assert scratch.is_dir()
        assert ks.path.parent == scratch

    assert not scratch.exists()
