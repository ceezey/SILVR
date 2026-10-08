from datetime import date

from silver_bot.risk import KillSwitch, RiskConfig, RiskManagementEngine, RiskRequest, RiskState


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
    engine = RiskManagementEngine(RiskConfig(risk_per_trade=0.01))

    decision = engine.evaluate(request())

    assert decision.approved is True
    assert decision.position_size == 20
    assert decision.risk_amount == 100
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
    engine = RiskManagementEngine(RiskConfig(risk_per_trade=0.05, max_leverage=0.5))

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
