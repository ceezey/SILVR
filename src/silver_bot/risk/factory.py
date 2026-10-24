"""Build the risk engine from validated application settings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from silver_bot.config import AppConfig
from silver_bot.risk.engine import RiskManagementEngine
from silver_bot.risk.models import RiskConfig

if TYPE_CHECKING:
    from silver_bot.storage import PostgresStorage


def build_risk_config(config: AppConfig) -> RiskConfig:
    """Return risk limits and the kill-switch path from settings."""

    return RiskConfig(
        risk_per_trade=config.max_risk_per_trade,
        max_daily_loss=config.max_daily_loss,
        max_leverage=config.max_leverage,
        kill_switch_path=config.kill_switch_path if config.kill_switch_enabled else None,
    )


def build_risk_engine(config: AppConfig, storage: PostgresStorage | None = None) -> RiskManagementEngine:
    """Return a risk engine whose limits and kill switch come from settings.

    `storage` must already be initialized. When given, daily loss, loss streak,
    trade count and open positions persist across restarts.
    """

    return RiskManagementEngine(build_risk_config(config), state_store=storage)
