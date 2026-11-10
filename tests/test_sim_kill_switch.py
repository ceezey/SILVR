import inspect
from datetime import UTC, datetime
from pathlib import Path

import pytest

from silvr.backtest.sim_kill_switch import SimulatedKillSwitch
from silvr.risk import KillSwitch, RiskConfig, RiskManagementEngine, RiskRequest

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


DAY1 = datetime(2026, 1, 2, 10, 0, tzinfo=UTC)
DAY2 = datetime(2026, 1, 3, 0, 0, tzinfo=UTC)
DAILY_LOSS = "Max daily loss limit reached"


def request(at: datetime) -> RiskRequest:
    return RiskRequest(
        equity=15_000.0, entry_price=100.0, stop_loss=98.0, take_profit=None, direction="LONG", signal_day=at.date()
    )


def lose_the_daily_limit(kill_switch: KillSwitch) -> RiskManagementEngine:
    """A trend-profile risk engine that has lost 2% on DAY1, as the trend engine drives it."""

    risk = RiskManagementEngine(RiskConfig.trend(), kill_switch=kill_switch)
    risk.reserve_trade(DAY1.date())
    risk.release_trade(realized_pnl=-400.0, day=DAY1.date())  # 2% of 15,000 is 300
    return risk


def test_trip_blocks_the_day_and_clears_at_the_next_utc_day() -> None:
    with SimulatedKillSwitch() as ks:
        ks.now = DAY1
        risk = lose_the_daily_limit(ks)

        assert risk.evaluate(request(DAY1)).reason == DAILY_LOSS
        assert risk.evaluate(request(DAY1)).reason == "Kill switch is active"
        assert ks.reset_if_new_day(DAY1.replace(hour=23, minute=59)) is False
        assert risk.evaluate(request(DAY1)).reason == "Kill switch is active"

        assert ks.reset_if_new_day(DAY2) is True
        assert risk.evaluate(request(DAY2)).approved
        assert ks.trips == [{"reason": DAILY_LOSS, "tripped_at": DAY1, "reset_at": DAY2}]


def test_plain_kill_switch_has_no_reset_and_blocks_every_day(tmp_path: Path) -> None:
    ks = KillSwitch(tmp_path / "KS")
    risk = lose_the_daily_limit(ks)

    assert risk.evaluate(request(DAY1)).reason == DAILY_LOSS
    assert not hasattr(ks, "reset_if_new_day")
    assert risk.evaluate(request(DAY2)).reason == "Kill switch is active"
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
