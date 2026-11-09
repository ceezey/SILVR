"""Read-only status collection for the operator dashboard (PRD-F13, silvr-cr-001)."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg

from silvr.config import AppConfig, ConfigError, load_config
from silvr.monitoring.audit import redact_secrets
from silvr.risk.kill_switch import KillSwitch
from silvr.storage.postgres import CONNECT_TIMEOUT_SECONDS

PANEL_TITLES: tuple[str, ...] = (
    "MODE & SAFETY",
    "READINESS",
    "EVIDENCE REPORTS",
    "RISK BUDGET",
    "POSITIONS / TRADES",
    "ALERTS",
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
LADDER_STEPS: tuple[str, ...] = ("Backtest", "Out-of-sample", "Paper", "Demo", "Live")
NEXT_TEXT: tuple[str, ...] = (
    "Next: run a backtest (runbook-backtest.md steps 5 and 6)",
    "Next: run a backtest (runbook-backtest.md steps 5 and 6)",
    "Next: paper trading (not available yet, G-3)",
    "Next: refresh demo readiness  python -m silvr.demo_readiness (runbook-demo-testnet.md steps 3 and 4)",
)
ALL_GATES_PASS = "All evidence gates pass. Live trading stays blocked (PRD-F12)."
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
RISK_PREFIX = "Risk rejected: "
SIGNAL_TEXT = "Strategy signal detected. Passing to risk engine."

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
        lambda: _readiness(root, now),
        lambda: _evidence(root),
        lambda: _risk_budget(config, now),
        lambda: _positions(config),
        lambda: _alerts(root),
    )
    panels = []
    degraded = 0
    for title, collect in zip(PANEL_TITLES, collectors):
        try:
            rows = collect()
        except Exception as exc:  # one unreadable source must not blank the page (AC-23.7)
            rows = [row("err", "unreadable", type(exc).__name__)]
            degraded += 1
        panels.append({"title": title, "rows": rows})
    try:
        ladder = _ladder(panels[2]["rows"], panels[1]["rows"])
    except Exception as exc:  # a broken panel makes the ladder unreadable, never a guess (AC-23.7)
        ladder = {"steps": [row("err", "unreadable", type(exc).__name__)], "next": None, "next_text": ""}
        degraded += 1
    try:
        restraint = _restraint(config, now)
    except Exception as exc:  # never blank the page (AC-23.7); the panels above already count a database failure
        restraint = _restraint_off(f"not available: restraint unreadable ({type(exc).__name__})")
    return {
        "generated_at": _format_time(now),
        "root": str(root),
        "panels": panels,
        "ladder": ladder,
        "restraint": restraint,
        "degraded": degraded,
    }


def _ladder(evidence_rows: list[Row], readiness_rows: list[Row]) -> dict[str, Any]:
    """Build the five-step evidence ladder from rows already collected."""

    steps = [_strategy_step(label, stem, evidence_rows) for label, stem in zip(LADDER_STEPS, STRATEGY_REPORTS)]
    steps.append(_demo_step(readiness_rows))
    steps.append(row("off", LADDER_STEPS[4], "blocked (PRD-F12)"))
    next_index = next((index for index, step in enumerate(steps[:4]) if step["state"] != "ok"), None)
    next_text = ALL_GATES_PASS if next_index is None else NEXT_TEXT[next_index]
    # Gates clear (silvr-cr-004 V-3a): steps 1 to 4 in state ok. Live is never counted.
    gates_clear = sum(1 for step in steps[:4] if step["state"] == "ok")
    return {"steps": steps, "next": next_index, "next_text": next_text, "gates_clear": gates_clear}


def _find_row(rows: list[Row], label: str) -> Row:
    for item in rows:
        if item["label"] == label:
            return item
    raise KeyError(label)


def _strategy_step(label: str, stem: str, evidence_rows: list[Row]) -> Row:
    found = _find_row(evidence_rows, stem)
    if found["state"] == "ok":
        return row("ok", label, found["text"].split(",")[0])
    if found["text"] == "missing":
        return row("off", label, "missing")
    return row("err", label, found["text"].split(",")[0])


def _demo_step(readiness_rows: list[Row]) -> Row:
    found = _find_row(readiness_rows, "demo")
    state, text = found["state"], found["text"]
    if state == "ok":
        return row("ok", LADDER_STEPS[3], "READY")
    if state == "warn":
        return row("warn", LADDER_STEPS[3], "READY · stale")
    if state == "err" and text.startswith("NOT READY"):
        return row("err", LADDER_STEPS[3], text)
    if text == "missing":
        return row("off", LADDER_STEPS[3], "missing")
    return row("err", LADDER_STEPS[3], "unreadable")


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


def _readiness(root: Path, now: datetime) -> list[Row]:
    reports = root / "reports"
    newest_evidence = max(
        (path.stat().st_mtime for path in (reports / f"{stem}.json" for stem in STRATEGY_REPORTS) if path.is_file()),
        default=None,
    )
    rows: list[Row] = []
    for name, stem in READINESS_REPORTS:
        data, problem, _ = _read_json_object(reports / f"{stem}.json")
        if data is None:
            rows.append(row("err", name, problem))
            continue
        ready = data.get("ready") is True
        generated_row, stale = _generated_row(data.get("generated_at"), newest_evidence, now)
        text = "READY" if ready else "NOT READY"
        state = "ok" if ready else "err"
        if stale:
            text += " · stale"
            state = "warn" if ready else "err"
        rows.append(row(state, name, text))
        rows.append(generated_row)
        checks = data.get("checks")
        for check in checks if isinstance(checks, list) else []:
            if isinstance(check, dict) and check.get("passed") is not True:
                rows.append(row("err", "", f"{check.get('name', 'unnamed check')}: {check.get('reason', 'no reason')}"))
    return rows


def _generated_row(value: Any, newest_evidence: float | None, now: datetime) -> tuple[Row, bool]:
    try:
        generated = _parse_time(value)
    except ValueError:
        return row("warn", "", "generated_at unreadable"), True
    text = f"generated {_format_time(generated)}"
    reasons = []
    if newest_evidence is not None and newest_evidence > generated.timestamp():
        reasons.append("evidence changed after this report")
    if now - generated > timedelta(hours=24):
        reasons.append("older than 24 hours")
    if reasons:
        return row("warn", "", f"{text}; stale: {'; '.join(reasons)}"), True
    return row("plain", "", text), False


def _evidence(root: Path) -> list[Row]:
    rows: list[Row] = []
    for stem in EVIDENCE_REPORTS:
        path = root / "reports" / f"{stem}.json"
        _, problem, stat = _read_json_object(path)
        if stat is None:
            rows.append(row("err", stem, "missing"))
            continue
        detail = f"{stat.st_size} B, modified {_format_time(datetime.fromtimestamp(stat.st_mtime, UTC))}"
        rows.append(row("err", stem, f"{detail}; {problem}") if problem else row("ok", stem, detail))
    return rows


def _risk_budget(config: AppConfig | None, now: datetime) -> list[Row]:
    if config is None:
        return [row("off", "", CONFIG_INVALID)]
    found = _query(
        config.database_url,
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
        row("plain", "max daily loss", f"{_number(config.max_daily_loss)} of equity"),
        row("plain", "max risk per trade", f"{_number(config.max_risk_per_trade)} of equity"),
    ]


def _positions(config: AppConfig | None) -> list[Row]:
    if config is None:
        return [row("off", "", CONFIG_INVALID)]
    database = config.database_url
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
    rows = [
        row("plain", "open positions", str(state[0][0]))
        if state
        else row("off", "open positions", "not available: no risk_state row")
    ]
    rows += [
        {
            **row("plain", f"SIM {_display_time(exit_time)}", f"{symbol} {direction} {_number(entry)} to {_number(exit_price)}, pnl {pnl:.2f}, {reason}"),
            "event": "closed trade",
        }
        for exit_time, symbol, direction, entry, exit_price, pnl, reason in trades
    ]
    rows += [
        {**row("plain", f"SIM {_display_time(timestamp)}", _event_text(event_type, message)), "event": event_type}
        for timestamp, event_type, message in events
    ]
    return rows


def _sentence(text: str) -> str:
    """End text with one full stop, keeping it exactly as stored otherwise."""

    return text if text.endswith(".") else text + "."


def _reason(message: str) -> str:
    """The stored risk_rejected message without its leading "Risk rejected: " (silvr-cr-004 V-6)."""

    return message.removeprefix(RISK_PREFIX)


def _event_text(event_type: str, message: str) -> str:
    """Dashboard wording for one paper event (DSD 1.4, silvr-cr-004 V-6); other events show as stored."""

    if event_type == "risk_rejected":
        reason = _reason(message)
        return f"Risk engine held. Setup declined: {_sentence(reason)}" if reason else "Risk engine held. Setup declined."
    if event_type == "signal_detected":
        return SIGNAL_TEXT
    return message


def _restraint_off(text: str) -> dict[str, Any]:
    return {"state": "off", "count": None, "text": text}


def _restraint(config: AppConfig | None, now: datetime) -> dict[str, Any]:
    """Count today's (UTC) risk_rejected paper events; a real count, never estimated (silvr-cr-004 V-3b).

    paper_events.timestamp is TEXT (the isoformat of the signal time, storage/postgres.py:76), so the
    SQL only narrows by date text (any UTC offset puts a UTC day within a day of its local date) and
    the day itself is decided here on the parsed value. Rows are not capped by RECENT_ROWS.
    """

    if config is None:
        return _restraint_off(CONFIG_INVALID)
    if config.database_url is None:
        return _restraint_off("not available: no database configured (G-3)")
    today = now.astimezone(UTC).date()
    since = (today - timedelta(days=1)).isoformat()  # digits and dashes from a date, never user input
    found = _query(
        config.database_url,
        'SELECT "timestamp", message FROM paper_events '
        f"WHERE event_type = 'risk_rejected' AND \"timestamp\" >= '{since}' ORDER BY id DESC",
    )
    if found is None:
        return _restraint_off("not available: paper_events table absent, no paper run (G-3)")
    held = [message for timestamp, message in found if _utc_day(timestamp) == today]
    if not held:
        return {"state": "ok", "count": 0, "text": "No setups held today."}
    noun = "setup" if len(held) == 1 else "setups"
    reason = _reason(held[0])  # newest row first (ORDER BY id DESC)
    text = f"Risk engine held {len(held)} {noun} today."
    if reason:
        text += f" Reason: {_sentence(reason)}"
    return {"state": "ok", "count": len(held), "text": text}


def _utc_day(value: Any) -> date | None:
    try:
        return _parse_time(value).astimezone(UTC).date()
    except ValueError:
        return None


def _alerts(root: Path) -> list[Row]:
    path = root / "logs" / "audit.jsonl"
    if not path.exists():
        return [row("off", "", "not available: no audit log yet")]
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - AUDIT_TAIL_BYTES))
        lines = handle.read().split(b"\n")
    lines.pop()  # empty after a final newline, else the line the bot is still writing
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
    if rows:
        return rows
    if size:
        return [row("off", "", "not available: no complete line in the last 64 KiB")]
    return [row("off", "", "not available: audit log is empty")]


def _read_json_object(path: Path) -> tuple[dict[str, Any] | None, str, os.stat_result | None]:
    """Return (object, "", stat) or (None, problem, stat) from one open of a JSON report.

    The stat is None only when the file is missing.
    """

    try:
        with path.open("rb") as handle:
            stat = os.fstat(handle.fileno())
            raw = handle.read()
    except FileNotFoundError:
        return None, "missing", None
    if not raw:
        return None, "empty", stat
    try:
        data = json.loads(raw)
    except ValueError:
        return None, "not valid JSON", stat
    if not isinstance(data, dict):
        return None, "not a JSON object", stat
    return data, "", stat


def _number(value: float) -> str:
    """Show a stored number exactly: whole values without ".0", others as repr."""

    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return repr(value)


def _query(database_url: str | None, sql: str) -> list[tuple[Any, ...]] | None:
    """Run one read-only query; None when no database is configured or the table is absent."""

    if database_url is None:
        return None
    with psycopg.connect(database_url, connect_timeout=CONNECT_TIMEOUT_SECONDS) as connection:
        connection.read_only = True
        try:
            return connection.execute(sql).fetchall()
        except psycopg.errors.UndefinedTable:
            return None


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
