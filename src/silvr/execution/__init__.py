"""Execution package.

Only paper execution is implemented. Real order execution remains disabled.
"""

from silvr.execution.models import (
    PaperEventType,
    PaperExecutionConfig,
    PaperLifecycleEvent,
    PaperOrder,
    PaperPosition,
)
from silvr.execution.paper_executor import PaperExecutionEngine
from silvr.execution.paper_trading import PaperTradingEngine, PaperTradingResult
from silvr.execution.trade_management import BasicTradeManager

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
