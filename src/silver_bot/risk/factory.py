"""Build the risk engine from validated application settings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from silver_bot.config import AppConfig
from silver_bot.risk.engine import RiskManagementEngine
from silver_bot.risk.models import RiskConfig

if TYPE_CHECKING:
    from silver_bot.storage import SQLiteStorage


def build_risk_engine(config: AppConfig, storage: SQLiteStorage | None = None) -> RiskManagementEngine:
    """Return a risk engine whose limits and kill switch come from settings.

    `storage` must already be initialized. When given, daily loss, loss streak,
    trade count and open positions persist across restarts.
    """

    risk_config = RiskConfig(
        risk_per_trade=config.max_risk_per_trade,
        max_daily_loss=config.max_daily_loss,
        max_leverage=config.max_leverage,
        kill_switch_path=config.kill_switch_path if config.kill_switch_enabled else None,
    )
    return RiskManagementEngine(risk_config, state_store=storage)
