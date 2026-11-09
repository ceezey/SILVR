import math
from datetime import date

import pytest

from silvr.config import load_config
from silvr.risk import KillSwitch, RiskConfig, RiskManagementEngine, RiskRequest, build_risk_engine

DAY = date(2026, 1, 2)


def engine(config: RiskConfig) -> RiskManagementEngine:
    """Engine with an in-memory kill switch (no filesystem)."""

    return RiskManagementEngine(config, kill_switch=KillSwitch())


def req(
    *,
    equity: float = 15_000,
    entry: float = 100.0,
    stop: float = 95.0,
    take_profit: float | None = 110.0,
    direction: str = "LONG",
    requested_size: float | None = None,
) -> RiskRequest:
    return RiskRequest(
        equity=equity,
        entry_price=entry,
        stop_loss=stop,
        take_profit=take_profit,
        direction=direction,
        signal_day=DAY,
        requested_size=requested_size,
    )


def test_default_profile_unchanged():
    d = engine(RiskConfig()).evaluate(req(take_profit=None))
    assert not d.approved and d.reason == "Take profit is required"


def test_trend_allows_no_take_profit():
    d = engine(RiskConfig.trend()).evaluate(
        req(entry=100.0, stop=65.0, take_profit=None, requested_size=1.0, equity=15_000)
    )
    assert d.approved and d.reward_to_risk == 0.0


def test_trend_caps_size_at_half_percent_risk():
    d = engine(RiskConfig.trend()).evaluate(
        req(entry=100.0, stop=65.0, take_profit=None, requested_size=10.0, equity=15_000)
    )
    assert d.position_size == pytest.approx(75.0 / 35.0) and d.risk_amount == pytest.approx(75.0)


def test_trend_keeps_requested_size_when_smaller():
    d = engine(RiskConfig.trend()).evaluate(
        req(entry=100.0, stop=65.0, take_profit=None, requested_size=1.0, equity=15_000)
    )
    assert d.position_size == 1.0


def test_trend_relative_min_stop():
    d = engine(RiskConfig.trend()).evaluate(req(entry=0.10, stop=0.09995, take_profit=None, requested_size=1.0))
    assert not d.approved and d.reason == "Stop-loss distance below configured minimum"
    assert engine(RiskConfig.trend()).evaluate(
        req(entry=0.10, stop=0.09, take_profit=None, requested_size=1.0)
    ).approved


def test_trend_no_consecutive_loss_trip():
    e = engine(RiskConfig.trend())
    for _ in range(5):
        e.reserve_trade(DAY)
        e.release_trade(realized_pnl=-10.0, day=DAY)
    assert not e.kill_switch.is_active()


def test_trend_profile_validation():
    with pytest.raises(ValueError):
        RiskConfig(profile="trend", minimum_stop_fraction=None)
    with pytest.raises(ValueError):
        RiskConfig(profile="other")
    with pytest.raises(ValueError):
        RiskConfig.trend(risk_per_trade=0.01)


def test_trend_values():
    c = RiskConfig.trend()
    assert (c.profile, c.max_trades_per_day, c.max_open_positions, c.minimum_stop_fraction) == ("trend", 135, 135, 0.001)
    assert (c.max_daily_loss, c.max_leverage, c.risk_per_trade) == (0.02, 3.0, 0.005)


def test_nonpositive_requested_size_rejected():
    for size in (0.0, -1.0):
        d = engine(RiskConfig.trend()).evaluate(req(stop=65.0, take_profit=None, requested_size=size))
        assert not d.approved


def test_trend_leverage_checked_on_final_size():
    # stop distance 0.15 on entry 100: the risk cap is 75 / 0.15 = 500 units = 3.33x leverage
    small = engine(RiskConfig.trend()).evaluate(req(entry=100.0, stop=99.85, take_profit=None, requested_size=400.0))
    assert small.approved and small.leverage == pytest.approx(400.0 * 100.0 / 15_000)
    big = engine(RiskConfig.trend()).evaluate(req(entry=100.0, stop=99.85, take_profit=None, requested_size=1000.0))
    assert not big.approved and big.reason == "Maximum leverage exceeded"
    assert big.leverage == pytest.approx(500.0 * 100.0 / 15_000)


def test_trend_evaluate_skips_consecutive_loss_check():
    e = engine(RiskConfig.trend())
    for _ in range(5):
        e.reserve_trade(DAY)
        e.release_trade(realized_pnl=-1.0, day=DAY)  # small losses: the daily-loss limit stays far away
    assert e.state.consecutive_losses == 5 > RiskConfig().max_consecutive_losses
    assert e.evaluate(req(stop=65.0, take_profit=None, requested_size=1.0)).approved
    assert not e.kill_switch.is_active()


def test_trend_rejects_nan_requested_size():
    d = engine(RiskConfig.trend()).evaluate(req(stop=65.0, take_profit=None, requested_size=math.nan))
    assert not d.approved and d.reason == "Requested size must be positive"


def test_trend_rejects_missing_or_wrong_side_stop():
    missing = engine(RiskConfig.trend()).evaluate(req(stop=None, take_profit=None, requested_size=1.0))
    assert not missing.approved and missing.reason == "Stop loss is required"
    above = engine(RiskConfig.trend()).evaluate(req(entry=100.0, stop=105.0, take_profit=None, requested_size=1.0))
    assert not above.approved and above.reason == "Invalid stop loss for trade direction"


@pytest.mark.parametrize("config", [RiskConfig(), RiskConfig.trend()], ids=["default", "trend"])
def test_nan_stop_rejected(config: RiskConfig):
    take_profit = None if config.profile == "trend" else 110.0
    d = engine(config).evaluate(req(stop=math.nan, take_profit=take_profit, requested_size=1.0))
    assert not d.approved and d.reason == "Invalid stop loss for trade direction"


def test_trend_daily_loss_check_still_rejects():
    e = engine(RiskConfig.trend())
    e.state.current_day = DAY
    e.state.daily_realized_pnl = -0.02 * 15_000  # exactly the 2% limit
    d = e.evaluate(req(stop=65.0, take_profit=None, requested_size=1.0, equity=15_000))
    assert not d.approved and d.reason == "Max daily loss limit reached"
    assert e.kill_switch.is_active()


@pytest.mark.parametrize(
    "override",
    [
        {"max_leverage": 3.01},
        {"max_daily_loss": 0.021},
        {"max_trades_per_day": 136},
        {"max_open_positions": 136},
        {"minimum_stop_fraction": 0.0009},
        {"max_leverage": math.nan},
        {"max_daily_loss": math.nan},
    ],
)
def test_trend_overrides_cannot_loosen_spec_limits(override: dict[str, float]):
    with pytest.raises(ValueError, match="trend profile"):
        RiskConfig.trend(**override)


def test_trend_overrides_may_tighten():
    c = RiskConfig.trend(
        max_leverage=2.0, max_daily_loss=0.01, max_trades_per_day=10, max_open_positions=10, minimum_stop_fraction=0.01
    )
    assert (c.max_leverage, c.max_daily_loss, c.max_trades_per_day, c.max_open_positions) == (2.0, 0.01, 10, 10)
    assert c.minimum_stop_fraction == 0.01


def test_default_profile_not_bound_by_trend_limits():
    assert RiskConfig(max_trades_per_day=200, max_open_positions=200).profile == "default"


def test_trend_still_enforces_kill_switch_and_trades_per_day():
    e = engine(RiskConfig.trend(max_trades_per_day=1))
    e.reserve_trade(DAY)
    assert e.evaluate(req(stop=65.0, take_profit=None, requested_size=1.0)).reason == "Max trades per day limit reached"
    e.kill_switch.trip("test")
    assert e.evaluate(req(stop=65.0, take_profit=None, requested_size=1.0)).reason == "Kill switch is active"


def test_factory_builds_default_profile(tmp_path):
    config = load_config(env_path=tmp_path / ".env", yaml_path=tmp_path / "missing.yaml", environ={})
    assert build_risk_engine(config).config.profile == "default"
