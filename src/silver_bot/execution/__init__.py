"""Execution package.

Only paper execution is implemented. Real order execution remains disabled.
"""

from silver_bot.execution.models import (
    PaperEventType,
    PaperExecutionConfig,
    PaperLifecycleEvent,
    PaperOrder,
    PaperPosition,
)
from silver_bot.execution.paper_executor import PaperExecutionEngine
from silver_bot.execution.paper_trading import PaperTradingEngine, PaperTradingResult
from silver_bot.execution.trade_management import BasicTradeManager

__all__ = [
    "BasicTradeManager",
    "PaperEventType",
    "PaperExecutionConfig",
    "PaperExecutionEngine",
    "PaperLifecycleEvent",
    "PaperOrder",
    "PaperPosition",
    "PaperTradingEngine",
    "PaperTradingResult",
]
