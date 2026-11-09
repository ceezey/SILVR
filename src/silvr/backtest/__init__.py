"""Backtesting tools for trend_ensemble."""

from silvr.backtest.metrics import calculate_metrics
from silvr.backtest.models import BacktestConfig, EquityPoint, ExitReason, TradeRecord
from silvr.backtest.validation import BacktestSplit, BacktestValidationSuite

__all__ = [
    "BacktestConfig",
    "BacktestSplit",
    "BacktestValidationSuite",
    "EquityPoint",
    "ExitReason",
    "TradeRecord",
    "calculate_metrics",
]
