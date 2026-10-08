"""Build the risk engine from validated application settings."""

from __future__ import annotations

from silver_bot.config import AppConfig
from silver_bot.risk.engine import RiskManagementEngine
from silver_bot.risk.models import RiskConfig


def build_risk_engine(config: AppConfig) -> RiskManagementEngine:
    """Return a risk engine whose limits and kill switch come from settings."""

    risk_config = RiskConfig(
        risk_per_trade=config.max_risk_per_trade,
        max_daily_loss=config.max_daily_loss,
        max_leverage=config.max_leverage,
        kill_switch_path=config.kill_switch_path if config.kill_switch_enabled else None,
    )
    return RiskManagementEngine(risk_config)
