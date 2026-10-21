"""Backtest performance metrics."""

from __future__ import annotations

import math
import statistics
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
    total_funding = sum(trade.funding for trade in trades)
    average_r = sum(trade.realized_r for trade in trades) / total_trades if trades else 0.0
    expectancy = net_profit / total_trades if trades else 0.0
    max_drawdown = max((point.drawdown for point in equity_curve), default=0.0)
    max_drawdown_percent = max_drawdown / initial_balance if initial_balance else 0.0
    return_percent = net_profit / initial_balance if initial_balance else 0.0
    average_win_r = sum(trade.realized_r for trade in winning) / len(winning) if winning else 0.0
    average_loss_r = sum(abs(trade.realized_r) for trade in losing) / len(losing) if losing else 0.0
    if average_loss_r:
        realized_rr = average_win_r / average_loss_r
    else:
        realized_rr = float("inf") if winning else 0.0
    r_stdev = statistics.stdev(trade.realized_r for trade in trades) if total_trades >= 2 else 0.0
    r_t_stat = average_r / (r_stdev / math.sqrt(total_trades)) if r_stdev else 0.0
    if return_percent <= 0:
        return_to_drawdown = 0.0
    elif max_drawdown_percent:
        return_to_drawdown = return_percent / max_drawdown_percent
    else:
        return_to_drawdown = float("inf")

    return {
        "total_trades": total_trades,
        "winning_trades": len(winning),
        "losing_trades": len(losing),
        "win_rate": len(winning) / total_trades if total_trades else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss else (float("inf") if gross_profit else 0.0),
        "expectancy": expectancy,
        "average_r": average_r,
        "max_drawdown": max_drawdown,
        "max_drawdown_percent": max_drawdown_percent,
        "max_consecutive_wins": _max_consecutive(trades, winning=True),
        "max_consecutive_losses": _max_consecutive(trades, winning=False),
        "total_fees": total_fees,
        "total_funding": total_funding,
        "net_profit": net_profit,
        "return_percent": return_percent,
        "average_win_r": average_win_r,
        "average_loss_r": average_loss_r,
        "realized_rr": realized_rr,
        "r_stdev": r_stdev,
        "r_t_stat": r_t_stat,
        "return_to_drawdown": return_to_drawdown,
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
