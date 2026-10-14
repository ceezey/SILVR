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
from silver_bot.backtest.runner import BacktestRunSummary, build_backtest_config, run_backtest
from silver_bot.backtest.validation import BacktestSplit, BacktestValidationSuite

__all__ = [
    "BacktestConfig",
    "BacktestEngine",
    "BacktestResult",
    "BacktestRunSummary",
    "BacktestSplit",
    "BacktestValidationSuite",
    "EquityPoint",
    "ExitReason",
    "PendingOrder",
    "TradeRecord",
    "build_backtest_config",
    "calculate_metrics",
    "export_backtest_result",
    "run_backtest",
]
