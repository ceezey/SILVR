"""Read-only status collection for the operator dashboard (PRD-F13, silverbot-cr-001)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from silver_bot.config import AppConfig, ConfigError, load_config
from silver_bot.monitoring.audit import redact_secrets
from silver_bot.risk.kill_switch import KillSwitch

PANEL_TITLES: tuple[str, ...] = (
    "MODE & SAFETY",
    "READINESS",
    "EVIDENCE REPORTS",
    "RISK BUDGET",
    "OPEN POSITIONS / RECENT TRADES",
    "ALERTS (logs/audit.jsonl)",
)
EVIDENCE_REPORTS: tuple[str, ...] = (
    "backtest_report",
    "out_of_sample_validation_report",
    "paper_trading_report",
    "live_readiness_report",
    "demo_readiness_report",
)
STRATEGY_REPORTS: tuple[str, ...] = EVIDENCE_REPORTS[:3]
READINESS_REPORTS: tuple[tuple[str, str], ...] = (
    ("live", "live_readiness_report"),
    ("demo", "demo_readiness_report"),
)
ALERT_STATES: dict[str, str] = {
    "risk_rejected": "warn",
    "signal_rejected": "warn",
    "kill_switch_active": "warn",
    "mode_unavailable": "warn",
    "error": "err",
}
AUDIT_TAIL_BYTES = 64 * 1024
AUDIT_EVENTS = 20
RECENT_ROWS = 10
NO_PAPER_RUN = "none recorded (no paper run, G-3)"
CONFIG_INVALID = "not available: configuration invalid"

Row = dict[str, str]


def row(state: str, label: str, text: str = "") -> Row:
    """Return one display row; state is ok, warn, err, off or plain."""

    return {"state": state, "label": label, "text": text}


def collect_status(
    root: str | Path,
    *,
    load: Callable[[], AppConfig] = load_config,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Read every dashboard source without writing anything."""

    root = Path(root)
    now = now or datetime.now(UTC)
    config: AppConfig | None = None
    config_error = ""
    try:
        config = load()
    except ConfigError as exc:
        config_error = str(exc)
    except Exception as exc:  # an unreadable .env or config.yaml must not blank the page
        config_error = f"unreadable: {type(exc).__name__}"
    collectors: tuple[Callable[[], list[Row]], ...] = (
        lambda: _banner(config, config_error, root),
        lambda: _readiness(root),
        lambda: _evidence(root),
        lambda: _risk_budget(config, root, now),
        lambda: _positions(config, root),
        lambda: _alerts(root),
    )
    panels = []
    for title, collect in zip(PANEL_TITLES, collectors):
        try:
            rows = collect()
        except Exception as exc:  # one unreadable source must not blank the page (AC-23.7)
            rows = [row("err", "unreadable", type(exc).__name__)]
        panels.append({"title": title, "rows": rows})
    return {"generated_at": _format_time(now), "panels": panels}


def _banner(config: AppConfig | None, config_error: str, root: Path) -> list[Row]:
    if config is None:
        return [row("err", "CONFIG", f"config invalid: {config_error}")]
    return [
        row("plain", "MODE", config.mode.value.upper()),
        _flag("LIVE", config.live_trading, on_state="err"),
        _flag("PAPER", config.paper_trading, on_state="ok"),
        _flag("DEMO", config.demo_trading, on_state="ok"),
        _kill_switch(config, root),
        row("plain", "NOTE", "settings as loaded by this page, not the state of a running bot (G-3)"),
    ]


def _flag(label: str, enabled: bool, *, on_state: str) -> Row:
    return row(on_state, label, "ON") if enabled else row("off", label, "OFF")


def _kill_switch(config: AppConfig, root: Path) -> Row:
    if not config.kill_switch_enabled:
        return row("off", "KILL", "disabled")
    if config.kill_switch_path is None:
        return row("warn", "KILL", "path not set (G-6)")
    path = _resolve(root, config.kill_switch_path)
    if not KillSwitch(path).is_active():
        return row("ok", "KILL", f"armed; {path.name} absent")
    return row("err", "KILL", "ACTIVE" + _trip_detail(path))


def _trip_detail(path: Path) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(data, dict):
        return ""
    return f": {data.get('reason', 'no reason')} at {data.get('tripped_at', 'unknown time')}"


def _readiness(root: Path) -> list[Row]:
    reports = root / "reports"
    newest_evidence = max(
        (path.stat().st_mtime for path in (reports / f"{stem}.json" for stem in STRATEGY_REPORTS) if path.is_file()),
        default=None,
    )
    rows: list[Row] = []
    for name, stem in READINESS_REPORTS:
        data, problem = _read_json_object(reports / f"{stem}.json")
        if data is None:
            rows.append(row("err", name, problem))
            continue
        ready = data.get("ready") is True
        rows.append(row("ok" if ready else "err", name, "READY" if ready else "NOT READY"))
        rows.append(_generated_row(data.get("generated_at"), newest_evidence))
        checks = data.get("checks")
        for check in checks if isinstance(checks, list) else []:
            if isinstance(check, dict) and check.get("passed") is not True:
                rows.append(row("err", "", f"{check.get('name', 'unnamed check')}: {check.get('reason', 'no reason')}"))
    return rows


def _generated_row(value: Any, newest_evidence: float | None) -> Row:
    try:
        generated = _parse_time(value)
    except ValueError:
        return row("warn", "", "generated_at unreadable")
    text = f"generated {_format_time(generated)}"
    if newest_evidence is not None and newest_evidence > generated.timestamp():
        return row("warn", "", f"{text}; stale: evidence changed after this report")
    return row("plain", "", text)


def _evidence(root: Path) -> list[Row]:
    rows: list[Row] = []
    for stem in EVIDENCE_REPORTS:
        path = root / "reports" / f"{stem}.json"
        _, problem = _read_json_object(path)
        if problem == "missing":
            rows.append(row("err", stem, "missing"))
            continue
        stat = path.stat()
        detail = f"{stat.st_size} B, modified {_format_time(datetime.fromtimestamp(stat.st_mtime, UTC))}"
        rows.append(row("err", stem, f"{detail}; {problem}") if problem else row("ok", stem, detail))
    return rows


def _risk_budget(config: AppConfig | None, root: Path, now: datetime) -> list[Row]:
    if config is None:
        return [row("off", "", CONFIG_INVALID)]
    found = _query(
        _resolve(root, config.database_path),
        "SELECT current_day, daily_realized_pnl, trades_today, consecutive_losses, open_positions, updated_at "
        "FROM risk_state WHERE id = 1",
    )
    if not found:
        return [row("off", "", "not available: risk_state empty, no running bot (G-3)")]
    day, pnl, trades, losses, open_positions, updated_at = found[0]
    today = now.astimezone(UTC).date().isoformat()
    day_row = row("plain", "day", str(day)) if day == today else row("warn", "day", f"{day}; stale: not today ({today} UTC)")
    return [
        day_row,
        row("plain", "daily realized pnl", f"{pnl:.2f}"),
        row("plain", "trades today", str(trades)),
        row("plain", "consecutive losses", str(losses)),
        row("plain", "open positions", str(open_positions)),
        row("plain", "updated", _display_time(updated_at)),
        row("plain", "max daily loss", f"{config.max_daily_loss:g} of equity"),
        row("plain", "max risk per trade", f"{config.max_risk_per_trade:g} of equity"),
    ]


def _positions(config: AppConfig | None, root: Path) -> list[Row]:
    if config is None:
        return [row("off", "", CONFIG_INVALID)]
    database = _resolve(root, config.database_path)
    state = _query(database, "SELECT open_positions FROM risk_state WHERE id = 1")
    trades = _query(
        database,
        "SELECT exit_time, symbol, direction, entry_price, exit_price, realized_pnl, exit_reason "
        f"FROM paper_trades ORDER BY exit_time DESC, id DESC LIMIT {RECENT_ROWS}",
    ) or []
    events = _query(
        database,
        f"SELECT timestamp, event_type, message FROM paper_events ORDER BY id DESC LIMIT {RECENT_ROWS}",
    ) or []
    if not state and not trades and not events:
        return [row("off", "", NO_PAPER_RUN)]
    rows = [row("plain", "open positions", str(state[0][0]) if state else "unknown: no risk_state row")]
    rows += [
        row("plain", f"SIM {_display_time(exit_time)}", f"{symbol} {direction} {entry:g} to {exit_price:g}, pnl {pnl:.2f}, {reason}")
        for exit_time, symbol, direction, entry, exit_price, pnl, reason in trades
    ]
    rows += [
        row("plain", f"SIM {_display_time(timestamp)}", f"{event_type}: {message}")
        for timestamp, event_type, message in events
    ]
    return rows


def _alerts(root: Path) -> list[Row]:
    path = root / "logs" / "audit.jsonl"
    if not path.exists():
        return [row("off", "", "not available: no audit log yet")]
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - AUDIT_TAIL_BYTES))
        lines = handle.read().split(b"\n")
    if size > AUDIT_TAIL_BYTES:
        lines = lines[1:]  # the seek may have cut the first line
    events: list[dict[str, Any]] = []
    unreadable = 0
    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            unreadable += 1
            continue
        if isinstance(event, dict):
            events.append(redact_secrets(event))
        else:
            unreadable += 1
    rows = [
        row(
            ALERT_STATES.get(str(event.get("event_type")), "ok"),
            _display_time(event.get("created_at")),
            f"{event.get('event_type', 'unknown')}: {event.get('message', '')}",
        )
        for event in events[-AUDIT_EVENTS:]
    ]
    if unreadable:
        rows.append(row("warn", "", f"unreadable lines: {unreadable}"))
    return rows or [row("off", "", "not available: audit log is empty")]


def _read_json_object(path: Path) -> tuple[dict[str, Any] | None, str]:
    """Return (object, "") or (None, problem) for a JSON report file."""

    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None, "missing"
    if not raw:
        return None, "empty"
    try:
        data = json.loads(raw)
    except ValueError:
        return None, "not valid JSON"
    if not isinstance(data, dict):
        return None, "not a JSON object"
    return data, ""


def _query(database: Path, sql: str) -> list[tuple[Any, ...]] | None:
    """Run one read-only query; None when the database file or table is absent."""

    if not database.is_file():
        return None
    connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
    try:
        return connection.execute(sql).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            return None
        raise
    finally:
        connection.close()


def _resolve(root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else root / candidate


def _parse_time(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _format_time(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _display_time(value: Any) -> str:
    try:
        return _format_time(_parse_time(value))
    except ValueError:
        return str(value)
