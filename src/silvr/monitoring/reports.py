"""Performance report and trade journal helpers."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from silvr.backtest.models import EquityPoint, TradeRecord
from silvr.monitoring.audit import AuditEvent, redact_secrets


def build_daily_performance_report(
    *,
    trades: Iterable[TradeRecord],
    rejected_signals: Iterable[Mapping[str, Any]],
    equity_curve: Iterable[EquityPoint] | None = None,
    audit_events: Iterable[AuditEvent] | None = None,
    report_date: date | None = None,
) -> dict[str, Any]:
    """Build a daily performance report for backtest or paper mode."""

    trade_list = list(trades)
    rejected_list = list(rejected_signals)
    equity_points = list(equity_curve or [])
    selected_date = report_date or _infer_report_date(trade_list, rejected_list)
    daily_trades = [trade for trade in trade_list if trade.exit_time.date() == selected_date]
    daily_rejections = [
        rejection for rejection in rejected_list if _timestamp_of(rejection).date() == selected_date
    ]
    pnl = sum(trade.realized_pnl for trade in daily_trades)
    winning = [trade for trade in daily_trades if trade.realized_pnl > 0]
    best_trade = max(daily_trades, key=lambda trade: trade.realized_pnl, default=None)
    worst_trade = min(daily_trades, key=lambda trade: trade.realized_pnl, default=None)
    relevant_equity = [
        point for point in equity_points if point.timestamp.date() == selected_date
    ]
    return {
        "date": selected_date.isoformat(),
        "trades_taken": len(daily_trades),
        "rejected_setups": len(daily_rejections),
        "pnl": pnl,
        "drawdown": max((point.drawdown for point in relevant_equity), default=0.0),
        "win_rate": len(winning) / len(daily_trades) if daily_trades else 0.0,
        "average_r": _average(trade.realized_r for trade in daily_trades),
        "best_trade": _trade_summary(best_trade),
        "worst_trade": _trade_summary(worst_trade),
        "rule_failures": _reason_counts(daily_rejections),
        "ml_decisions": _ml_decision_counts(daily_trades, daily_rejections, audit_events or []),
    }


def build_weekly_performance_report(
    *,
    trades: Iterable[TradeRecord],
    rejected_signals: Iterable[Mapping[str, Any]],
    equity_curve: Iterable[EquityPoint] | None = None,
    week_start: date | None = None,
) -> dict[str, Any]:
    """Build a weekly performance report for backtest or paper mode."""

    trade_list = list(trades)
    rejected_list = list(rejected_signals)
    start = week_start or _infer_report_date(trade_list, rejected_list)
    end = start.fromordinal(start.toordinal() + 6)
    weekly_trades = [
        trade for trade in trade_list if start <= trade.exit_time.date() <= end
    ]
    weekly_rejections = [
        rejection for rejection in rejected_list if start <= _timestamp_of(rejection).date() <= end
    ]
    winning = [trade for trade in weekly_trades if trade.realized_pnl > 0]
    losing = [trade for trade in weekly_trades if trade.realized_pnl < 0]
    gross_profit = sum(trade.realized_pnl for trade in winning)
    gross_loss = abs(sum(trade.realized_pnl for trade in losing))
    session_stats = _session_net_pnl(weekly_trades)
    equity_points = [
        point for point in list(equity_curve or []) if start <= point.timestamp.date() <= end
    ]
    return {
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "total_trades": len(weekly_trades),
        "net_pnl": sum(trade.realized_pnl for trade in weekly_trades),
        "win_rate": len(winning) / len(weekly_trades) if weekly_trades else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss else (float("inf") if gross_profit else 0.0),
        "average_r": _average(trade.realized_r for trade in weekly_trades),
        "max_drawdown": max((point.drawdown for point in equity_points), default=0.0),
        "best_session": _best_session(session_stats),
        "worst_session": _worst_session(session_stats),
        "repeated_rejection_reasons": _reason_counts(weekly_rejections),
    }


def build_trade_journal(trades: Iterable[TradeRecord]) -> list[dict[str, Any]]:
    """Build structured trade journal rows."""

    return [_trade_summary(trade, include_notes=True) for trade in trades]


def export_trade_journal(trades: Iterable[TradeRecord], path: str | Path) -> Path:
    """Export the trade journal as CSV."""

    rows = build_trade_journal(trades)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        output_path.write_text("", encoding="utf-8")
        return output_path
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return output_path


def export_report_json(report: dict[str, Any], path: str | Path) -> Path:
    """Export a report as JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(_json_safe(report), indent=2, sort_keys=True), encoding="utf-8")
    return output_path


def _infer_report_date(trades: list[TradeRecord], rejected: list[Mapping[str, Any]]) -> date:
    if trades:
        return trades[0].exit_time.date()
    if rejected:
        return _timestamp_of(rejected[0]).date()
    return datetime.now(UTC).date()


def _timestamp_of(record: Any) -> datetime:
    if isinstance(record, dict):
        value = record.get("timestamp") or record.get("created_at")
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value)
    return getattr(record, "timestamp", datetime.now(UTC))


def _reason_of(record: Any) -> str:
    if isinstance(record, dict):
        return str(record.get("reason", "unknown"))
    return str(getattr(record, "reason", "unknown"))


def _ml_decision_of(record: Any) -> str | None:
    if isinstance(record, dict):
        value = record.get("ml_decision")
    else:
        value = getattr(record, "ml_decision", None)
    return str(value) if value else None


def _reason_counts(records: Iterable[Any]) -> dict[str, int]:
    counter = Counter(_reason_of(record) for record in records)
    return dict(counter)


def _ml_decision_counts(
    trades: Iterable[TradeRecord],
    rejected: Iterable[Any],
    audit_events: Iterable[AuditEvent],
) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for trade in trades:
        if trade.ml_decision:
            counter[str(trade.ml_decision)] += 1
    for record in rejected:
        decision = _ml_decision_of(record)
        if decision:
            counter[decision] += 1
    for event in audit_events:
        if event.event_type == "ml_decision":
            decision = event.context.get("decision")
            if decision:
                counter[str(decision)] += 1
    return dict(counter)


def _session_net_pnl(trades: Iterable[TradeRecord]) -> dict[str, float]:
    stats: defaultdict[str, float] = defaultdict(float)
    for trade in trades:
        stats[trade.session_name] += trade.realized_pnl
    return dict(stats)


def _best_session(stats: dict[str, float]) -> dict[str, Any] | None:
    if not stats:
        return None
    session, pnl = max(stats.items(), key=lambda item: item[1])
    return {"session_name": session, "net_pnl": pnl}


def _worst_session(stats: dict[str, float]) -> dict[str, Any] | None:
    if not stats:
        return None
    session, pnl = min(stats.items(), key=lambda item: item[1])
    return {"session_name": session, "net_pnl": pnl}


def _trade_summary(trade: TradeRecord | None, *, include_notes: bool = False) -> dict[str, Any] | None:
    if trade is None:
        return None
    row = {
        "trade_id": trade.trade_id,
        "symbol": trade.symbol,
        "timeframe": trade.timeframe,
        "session_name": trade.session_name,
        "direction": trade.direction,
        "entry_time": trade.entry_time.isoformat(),
        "exit_time": trade.exit_time.isoformat(),
        "entry_price": trade.entry_price,
        "exit_price": trade.exit_price,
        "stop_loss": trade.stop_loss,
        "take_profit": trade.take_profit,
        "position_size": trade.position_size,
        "risk_amount": trade.risk_amount,
        "realized_pnl": trade.realized_pnl,
        "realized_r": trade.realized_r,
        "fees": trade.fees,
        "slippage": trade.slippage,
        "exit_reason": trade.exit_reason.value,
        "setup_quality_score": trade.setup_quality_score,
        "ml_probability": trade.ml_probability,
        "ml_decision": trade.ml_decision,
    }
    if include_notes:
        row["notes"] = trade.notes
    return row


def _average(values: Iterable[float]) -> float:
    items = [float(value) for value in values]
    return sum(items) / len(items) if items else 0.0


def _json_safe(value: Any) -> Any:
    value = redact_secrets(value)
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    if value == float("inf"):
        return "inf"
    return value
