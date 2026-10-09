import json
from datetime import date
from types import SimpleNamespace

import pytest

import silver_bot.risk.kill_switch as kill_switch_module
from silver_bot.config import load_config
from silver_bot.risk import KillSwitch, RiskConfig, RiskManagementEngine, RiskRequest, RiskState, build_risk_engine
from silver_bot.storage import SQLiteStorage


def request(
    *,
    equity: float = 10_000,
    entry: float | None = 100,
    stop: float | None = 95,
    target: float | None = 110,
    direction: str = "LONG",
) -> RiskRequest:
    return RiskRequest(
        equity=equity,
        entry_price=entry,
        stop_loss=stop,
        take_profit=target,
        direction=direction,
        signal_day=date(2026, 1, 2),
    )


def test_valid_position_sizing() -> None:
    engine = RiskManagementEngine(RiskConfig(risk_per_trade=0.005))

    decision = engine.evaluate(request())

    assert decision.approved is True
    assert decision.position_size == 10
    assert decision.risk_amount == 50
    assert decision.reward_to_risk == 2


def test_invalid_stop_loss_is_rejected() -> None:
    engine = RiskManagementEngine()

    decision = engine.evaluate(request(stop=105))

    assert decision.approved is False
    assert decision.reason == "Invalid stop loss for trade direction"


def test_missing_stop_loss_is_rejected() -> None:
    engine = RiskManagementEngine()

    decision = engine.evaluate(request(stop=None))

    assert decision.approved is False
    assert decision.reason == "Stop loss is required"


def test_low_reward_to_risk_is_rejected() -> None:
    engine = RiskManagementEngine(RiskConfig(minimum_reward_to_risk=2.0))

    decision = engine.evaluate(request(target=104))

    assert decision.approved is False
    assert decision.reason == "Reward-to-risk below configured minimum"


def test_daily_loss_lockout() -> None:
    state = RiskState(current_day=date(2026, 1, 2), daily_realized_pnl=-250)
    engine = RiskManagementEngine(RiskConfig(max_daily_loss=0.02), state=state)

    decision = engine.evaluate(request())

    assert decision.approved is False
    assert decision.reason == "Max daily loss limit reached"


def test_consecutive_loss_lockout() -> None:
    state = RiskState(consecutive_losses=3)
    engine = RiskManagementEngine(RiskConfig(max_consecutive_losses=3), state=state)

    decision = engine.evaluate(request())

    assert decision.approved is False
    assert decision.reason == "Max consecutive losses limit reached"


def test_max_trades_lockout() -> None:
    state = RiskState(current_day=date(2026, 1, 2), trades_today=3)
    engine = RiskManagementEngine(RiskConfig(max_trades_per_day=3), state=state)

    decision = engine.evaluate(request())

    assert decision.approved is False
    assert decision.reason == "Max trades per day limit reached"


def test_max_open_positions_lockout() -> None:
    state = RiskState(open_positions=1)
    engine = RiskManagementEngine(RiskConfig(max_open_positions=1), state=state)

    decision = engine.evaluate(request())

    assert decision.approved is False
    assert decision.reason == "Max open positions limit reached"


def test_maximum_leverage_rejection() -> None:
    engine = RiskManagementEngine(RiskConfig(risk_per_trade=0.005, max_leverage=0.4))

    decision = engine.evaluate(request(entry=100, stop=99, target=103))

    assert decision.approved is False
    assert decision.reason == "Maximum leverage exceeded"


def test_kill_switch_active(tmp_path) -> None:
    kill_file = tmp_path / "KILL_SWITCH"
    kill_file.write_text("stop", encoding="utf-8")
    engine = RiskManagementEngine(kill_switch=KillSwitch(kill_file))

    decision = engine.evaluate(request())

    assert decision.approved is False
    assert decision.reason == "Kill switch is active"


def test_risk_per_trade_above_half_percent_is_rejected() -> None:
    with pytest.raises(ValueError, match="risk_per_trade"):
        RiskConfig(risk_per_trade=0.006)


def test_risk_per_trade_at_half_percent_is_allowed() -> None:
    assert RiskConfig(risk_per_trade=0.005).risk_per_trade == 0.005


def test_build_risk_engine_carries_settings_caps(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "MAX_RISK_PER_TRADE=0.004",
                "MAX_DAILY_LOSS=0.01",
                "MAX_LEVERAGE=2",
                "KILL_SWITCH_ENABLED=true",
                f"KILL_SWITCH_PATH={tmp_path / 'KILL_SWITCH'}",
            ]
        ),
        encoding="utf-8",
    )
    config = load_config(env_path=env_path, yaml_path=tmp_path / "missing.yaml", environ={})

    engine = build_risk_engine(config)

    assert engine.config.risk_per_trade == 0.004
    assert engine.config.max_daily_loss == 0.01
    assert engine.config.max_leverage == 2
    assert engine.kill_switch.path == tmp_path / "KILL_SWITCH"


def test_build_risk_engine_ignores_kill_switch_path_when_disabled(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(f"KILL_SWITCH_PATH={tmp_path / 'KILL_SWITCH'}\n", encoding="utf-8")
    config = load_config(env_path=env_path, yaml_path=tmp_path / "missing.yaml", environ={})

    engine = build_risk_engine(config)

    assert engine.kill_switch.path is None


def test_kill_switch_directory_path_is_active(tmp_path) -> None:
    folder = tmp_path / "KILL_SWITCH"
    folder.mkdir()

    assert KillSwitch(folder).is_active() is True


def test_kill_switch_unreadable_path_is_active(tmp_path, monkeypatch) -> None:
    def denied(path):
        raise PermissionError("denied")

    monkeypatch.setattr(kill_switch_module, "os", SimpleNamespace(stat=denied))

    assert KillSwitch(tmp_path / "KILL_SWITCH").is_active() is True


def test_kill_switch_parent_is_a_file_is_active(tmp_path) -> None:
    parent = tmp_path / "not_a_dir"
    parent.write_text("x", encoding="utf-8")

    assert KillSwitch(parent / "KILL_SWITCH").is_active() is True


def test_kill_switch_missing_file_is_inactive(tmp_path) -> None:
    assert KillSwitch(tmp_path / "KILL_SWITCH").is_active() is False


def test_kill_switch_trip_writes_reason_and_timestamp(tmp_path) -> None:
    switch = KillSwitch(tmp_path / "nested" / "KILL_SWITCH")

    switch.trip("Max daily loss limit reached")

    payload = json.loads((tmp_path / "nested" / "KILL_SWITCH").read_text(encoding="utf-8"))
    assert payload["reason"] == "Max daily loss limit reached"
    assert payload["tripped_at"].endswith("+00:00")
    assert switch.is_active() is True


def test_kill_switch_second_trip_keeps_first_reason(tmp_path) -> None:
    switch = KillSwitch(tmp_path / "KILL_SWITCH")
    switch.trip("first")
    switch.trip("second")

    payload = json.loads((tmp_path / "KILL_SWITCH").read_text(encoding="utf-8"))
    assert payload["reason"] == "first"


def test_kill_switch_without_path_trip_is_noop() -> None:
    switch = KillSwitch(None)
    switch.trip("anything")

    assert switch.is_active() is False


def test_consecutive_losses_trip_kill_switch(tmp_path) -> None:
    kill_file = tmp_path / "KILL_SWITCH"
    engine = RiskManagementEngine(RiskConfig(max_consecutive_losses=3, kill_switch_path=kill_file))
    day = date(2026, 1, 2)

    for _ in range(3):
        engine.reserve_trade(day)
        engine.release_trade(realized_pnl=-10, day=day)

    assert kill_file.exists()
    assert json.loads(kill_file.read_text(encoding="utf-8"))["reason"] == "Max consecutive losses limit reached"
    assert engine.evaluate(request()).reason == "Kill switch is active"


def test_daily_loss_rejection_trips_kill_switch(tmp_path) -> None:
    kill_file = tmp_path / "KILL_SWITCH"
    state = RiskState(current_day=date(2026, 1, 2), daily_realized_pnl=-250)
    engine = RiskManagementEngine(RiskConfig(max_daily_loss=0.02, kill_switch_path=kill_file), state=state)

    decision = engine.evaluate(request())

    assert decision.reason == "Max daily loss limit reached"
    assert json.loads(kill_file.read_text(encoding="utf-8"))["reason"] == "Max daily loss limit reached"


def risk_storage(tmp_path) -> SQLiteStorage:
    storage = SQLiteStorage(tmp_path / "risk.sqlite3")
    storage.initialize()
    return storage


def test_risk_state_survives_engine_restart(tmp_path) -> None:
    storage = risk_storage(tmp_path)
    day = date(2026, 1, 2)
    first = RiskManagementEngine(state_store=storage)
    first.reserve_trade(day)
    first.release_trade(realized_pnl=-50, day=day)

    second = RiskManagementEngine(state_store=storage)

    assert second.state == RiskState(
        current_day=day,
        daily_realized_pnl=-50,
        consecutive_losses=1,
        trades_today=1,
        open_positions=0,
    )


def test_restart_does_not_reset_consecutive_loss_limit(tmp_path) -> None:
    storage = risk_storage(tmp_path)
    day = date(2026, 1, 2)
    first = RiskManagementEngine(RiskConfig(max_consecutive_losses=3), state_store=storage)
    for _ in range(3):
        first.reserve_trade(day)
        first.release_trade(realized_pnl=-10, day=day)

    second = RiskManagementEngine(RiskConfig(max_consecutive_losses=3), state_store=storage)

    assert second.evaluate(request()).reason == "Max consecutive losses limit reached"


def test_corrupt_risk_state_halts_trading(tmp_path) -> None:
    import sqlite3

    storage = risk_storage(tmp_path)
    storage.save_risk_state(RiskState(current_day=date(2026, 1, 2)))
    connection = sqlite3.connect(storage.database_path)
    try:
        connection.execute("UPDATE risk_state SET open_positions = -3")
        connection.commit()
    finally:
        connection.close()

    engine = RiskManagementEngine(state_store=storage)
    decision = engine.evaluate(request())

    assert decision.approved is False
    assert decision.reason == "Risk state could not be loaded; trading halted"


def test_build_risk_engine_attaches_storage(tmp_path) -> None:
    storage = risk_storage(tmp_path)
    config = load_config(env_path=tmp_path / ".env", yaml_path=tmp_path / "missing.yaml", environ={})

    engine = build_risk_engine(config, storage)
    engine.reserve_trade(date(2026, 1, 2))

    assert storage.load_risk_state().trades_today == 1


def test_engine_without_store_does_not_persist(tmp_path) -> None:
    engine = RiskManagementEngine()
    engine.reserve_trade(date(2026, 1, 2))

    assert engine.state_store is None


def test_loss_is_persisted_even_if_kill_switch_trip_fails(tmp_path) -> None:
    storage = risk_storage(tmp_path)
    engine = RiskManagementEngine(RiskConfig(max_consecutive_losses=1), state_store=storage)

    def failing_trip(reason: str) -> None:
        raise OSError("read-only filesystem")

    engine.kill_switch.trip = failing_trip
    day = date(2026, 1, 2)
    engine.reserve_trade(day)

    with pytest.raises(OSError):
        engine.release_trade(realized_pnl=-10, day=day)

    saved = storage.load_risk_state()
    assert saved.consecutive_losses == 1
    assert saved.daily_realized_pnl == -10
    assert saved.open_positions == 0


def test_risk_state_load_error_is_logged(tmp_path, caplog) -> None:
    import sqlite3

    storage = risk_storage(tmp_path)
    storage.save_risk_state(RiskState(current_day=date(2026, 1, 2)))
    connection = sqlite3.connect(storage.database_path)
    try:
        connection.execute("UPDATE risk_state SET trades_today = -1")
        connection.commit()
    finally:
        connection.close()

    with caplog.at_level("ERROR", logger="silver_bot.risk.engine"):
        RiskManagementEngine(state_store=storage)

    assert "risk state could not be loaded" in caplog.text
    assert "trades_today" in caplog.text


from silver_bot.config import AppConfig, TradingMode
from silver_bot.risk import build_risk_config


def test_build_risk_config_maps_settings(tmp_path) -> None:
    config = AppConfig(
        mode=TradingMode.BACKTEST,
        paper_trading=False,
        kill_switch_enabled=True,
        kill_switch_path=tmp_path / "KILL_SWITCH",
        max_risk_per_trade=0.004,
        max_daily_loss=0.01,
        max_leverage=2.0,
    )

    risk = build_risk_config(config)

    assert risk.kill_switch_path == tmp_path / "KILL_SWITCH"
    assert (risk.risk_per_trade, risk.max_daily_loss, risk.max_leverage) == (0.004, 0.01, 2.0)
    assert build_risk_engine(config).config == risk
