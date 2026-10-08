from datetime import date

import pytest

from silver_bot.config import load_config
from silver_bot.risk import KillSwitch, RiskConfig, RiskManagementEngine, RiskRequest, RiskState, build_risk_engine


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
