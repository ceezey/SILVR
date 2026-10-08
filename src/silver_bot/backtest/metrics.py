"""Backtest performance metrics."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from silver_bot.backtest.models import EquityPoint, TradeRecord


def calculate_metrics(
    trades: list[TradeRecord],
    equity_curve: list[EquityPoint],
    *,
    initial_balance: float,
) -> dict[str, Any]:
    """Calculate core backtest metrics."""

    total_trades = len(trades)
    winning = [trade for trade in trades if trade.realized_pnl > 0]
    losing = [trade for trade in trades if trade.realized_pnl < 0]
    gross_profit = sum(trade.realized_pnl for trade in winning)
    gross_loss = abs(sum(trade.realized_pnl for trade in losing))
    net_profit = sum(trade.realized_pnl for trade in trades)
    total_fees = sum(trade.fees for trade in trades)
    average_r = sum(trade.realized_r for trade in trades) / total_trades if trades else 0.0
    expectancy = net_profit / total_trades if trades else 0.0
    max_drawdown = max((point.drawdown for point in equity_curve), default=0.0)

    return {
        "total_trades": total_trades,
        "winning_trades": len(winning),
        "losing_trades": len(losing),
        "win_rate": len(winning) / total_trades if total_trades else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss else (float("inf") if gross_profit else 0.0),
        "expectancy": expectancy,
        "average_r": average_r,
        "max_drawdown": max_drawdown,
        "max_drawdown_percent": max_drawdown / initial_balance if initial_balance else 0.0,
        "max_consecutive_wins": _max_consecutive(trades, winning=True),
        "max_consecutive_losses": _max_consecutive(trades, winning=False),
        "total_fees": total_fees,
        "net_profit": net_profit,
        "return_percent": net_profit / initial_balance if initial_balance else 0.0,
        "session_performance": _session_metrics(trades),
    }


def _max_consecutive(trades: list[TradeRecord], *, winning: bool) -> int:
    best = 0
    current = 0
    for trade in trades:
        matched = trade.realized_pnl > 0 if winning else trade.realized_pnl < 0
        if matched:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def _session_metrics(trades: list[TradeRecord]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[TradeRecord]] = defaultdict(list)
    for trade in trades:
        grouped[trade.session_name].append(trade)

    metrics: dict[str, dict[str, float]] = {}
    for session_name, session_trades in grouped.items():
        winners = [trade for trade in session_trades if trade.realized_pnl > 0]
        losers = [trade for trade in session_trades if trade.realized_pnl < 0]
        gross_profit = sum(trade.realized_pnl for trade in winners)
        gross_loss = abs(sum(trade.realized_pnl for trade in losers))
        metrics[session_name] = {
            "total_trades": len(session_trades),
            "win_rate": len(winners) / len(session_trades) if session_trades else 0.0,
            "profit_factor": gross_profit / gross_loss if gross_loss else (float("inf") if gross_profit else 0.0),
            "average_r": sum(trade.realized_r for trade in session_trades) / len(session_trades),
            "net_profit": sum(trade.realized_pnl for trade in session_trades),
        }
    return metrics
