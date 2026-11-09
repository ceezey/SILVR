"""Event-driven backtesting tools."""

from silvr.backtest.engine import BacktestEngine
from silvr.backtest.metrics import calculate_metrics
from silvr.backtest.models import (
    BacktestConfig,
    BacktestResult,
    EquityPoint,
    ExitReason,
    PendingOrder,
    TradeRecord,
)
from silvr.backtest.reporting import export_backtest_result
from silvr.backtest.runner import BacktestRunSummary, build_backtest_config, run_backtest
from silvr.backtest.validation import BacktestSplit, BacktestValidationSuite

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
