"""Application startup for the current safe Phase 1 scaffold."""

from __future__ import annotations

from silver_bot.config import ConfigError, load_config
from silver_bot.monitoring import StructuredAuditLogger
from silver_bot.storage import SQLiteStorage
from silver_bot.utils.logging import get_logger


logger = get_logger(__name__)


def main() -> int:
    """Load configuration and initialize local storage.

    Phase 1 intentionally starts only the local application foundation. It does
    not connect to an exchange or place orders.
    """

    try:
        config = load_config()
    except ConfigError as exc:
        logger.error("configuration rejected: %s", exc)
        return 2

    storage = SQLiteStorage(config.database_path)
    storage.initialize()
    audit = StructuredAuditLogger("logs/audit.jsonl")
    audit.log(
        "bot_started",
        "Silver bot initialized",
        context={
            "mode": config.mode.value,
            "paper_trading": config.paper_trading,
            "database_path": str(config.database_path),
            "ml_filter_enabled": config.ml_filter_enabled,
            "telegram_enabled": config.telegram_enabled,
        },
    )
    logger.info(
        "silver bot initialized",
        extra={
            "mode": config.mode.value,
            "paper_trading": config.paper_trading,
            "database_path": str(config.database_path),
        },
    )
    audit.log("bot_stopped", "Silver bot startup command completed", context={"mode": config.mode.value})
    return 0
