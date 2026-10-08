"""Event-driven backtesting tools."""

from silver_bot.backtest.engine import BacktestEngine
from silver_bot.backtest.metrics import calculate_metrics
from silver_bot.backtest.models import (
    BacktestConfig,
    BacktestResult,
    EquityPoint,
    ExitReason,
    PendingOrder,
    TradeRecord,
)
from silver_bot.backtest.reporting import export_backtest_result
from silver_bot.backtest.validation import BacktestSplit, BacktestValidationSuite

__all__ = [
    "BacktestConfig",
    "BacktestEngine",
    "BacktestResult",
    "BacktestSplit",
    "BacktestValidationSuite",
    "EquityPoint",
    "ExitReason",
    "PendingOrder",
    "TradeRecord",
    "calculate_metrics",
    "export_backtest_result",
]
