"""Read-only status collection for the operator dashboard (PRD-F13, silvr-cr-001)."""

from __future__ import annotations

import json
import math
import os
import re
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
    "FORWARD TEST",  # silvr-cr-005: last collected, shown after EVIDENCE REPORTS (see LAYOUT)
    "ANALYTICS",  # silvr-cr-006: appended last so indexes 0..6 do not move; shown after FORWARD TEST
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
FORWARD_NEXT = "Next: forward test, one verdict after 2027-11-10 (no tuning on data already seen)"  # silvr-cr-006 V-9
GATE_DETAILS: tuple[str, str] = ("trend_ensemble/out_of_sample_validation_report", "trend_ensemble/promotion_gate")
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
FORWARD_FILE = Path("reports") / "trend_ensemble_forward" / "forward_progress.json"
FORWARD_START = "2026-11-11"
FORWARD_DAYS = 365
VERDICT_DATE = "2027-11-10"
FORWARD_NOTE = "Progress only. No verdict until 2027-11-10. Do not change the strategy because of this number."
FORWARD_OK = ("running", "verdict PASS")
FORWARD_DECIDED = ("verdict PASS", "verdict FAIL")  # also any "ended: ..." or "void: ..."
NOT_AVAILABLE = "not available: no usable value in the progress file"
ANALYTICS_DIR = Path("reports") / "trend_ensemble"
GATE_FILE = "promotion_gate.json"
VALIDATION_FILE = "out_of_sample_validation_report.json"
SEGMENTS: tuple[tuple[str, str], ...] = (
    ("training", "TRAINING"),
    ("validation", "VALIDATION"),
    ("final_test", "FINAL TEST"),
)
SEGMENT_METRICS: tuple[str, ...] = (
    "period",
    "trades",
    "net",
    "return",
    "profit factor",
    "average R",
    "win rate",
    "max drawdown",
    "max drawdown %",
    "fees + funding",
    "weekly net vs target",
    "losing weeks",
    "kill switch trips",
)
WEEKLY_METRIC = SEGMENT_METRICS.index("weekly net vs target")
ANALYTICS_NOTE = "Backtest on past data, simulated account. A FAIL means no edge was found; the strategy is not traded."
NA = "not available"
RISK_PREFIX = "Risk rejected: "
SIGNAL_TEXT = "Strategy signal detected. Passing to risk engine."

Row = dict[str, Any]  # state, label, text; some rows carry structured extras ("event", "kind", "cells", ...)


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
        lambda: _forward(root),
        lambda: _analytics(root),
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
        ladder = _ladder(panels[2]["rows"], panels[1]["rows"], panels[7]["rows"])
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


def _ladder(evidence_rows: list[Row], readiness_rows: list[Row], analytics_rows: list[Row]) -> dict[str, Any]:
    """Build the five-step evidence ladder from rows already collected.

    With the counted gate run present (an ANALYTICS verdict row, silvr-cr-006 V-9) steps 1 and 2 read it
    instead of the two evidence reports; without it they read the reports exactly as before.
    """

    verdict = next((item for item in analytics_rows if item["label"] == "verdict"), None)
    if verdict is None:
        steps = [_strategy_step(label, stem, evidence_rows) for label, stem in zip(LADDER_STEPS, STRATEGY_REPORTS)]
    else:
        steps = [*_gate_steps(verdict), _strategy_step(LADDER_STEPS[2], STRATEGY_REPORTS[2], evidence_rows)]
    steps.append(_demo_step(readiness_rows))
    steps.append(row("off", LADDER_STEPS[4], "blocked (PRD-F12)"))
    next_index = next((index for index, step in enumerate(steps[:4]) if step["state"] != "ok"), None)
    next_text = ALL_GATES_PASS if next_index is None else NEXT_TEXT[next_index]
    if verdict is not None and next_index == 1:
        next_text = FORWARD_NEXT  # a trend FAIL: the next evidence is the forward test, not another backtest
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


def _gate_steps(verdict: Row) -> list[Row]:
    """Steps 1 and 2 from the counted gate run; each names its file under trend_ensemble/ (V-9)."""

    if verdict["state"] == "ok":
        outcome = row("ok", LADDER_STEPS[1], "GATE PASS")
    else:
        counted = re.search(r"(\d+) of (\d+) criteria passed", verdict["text"])
        suffix = f" · {counted[1]} of {counted[2]}" if counted else ""
        outcome = row("err", LADDER_STEPS[1], f"GATE FAIL{suffix}")
    return [
        {**row("ok", LADDER_STEPS[0], "trend_ensemble run"), "detail": GATE_DETAILS[0]},
        {**outcome, "detail": GATE_DETAILS[1]},
    ]


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


def _forward(root: Path) -> list[Row]:
    """The forward test's monthly progress file as rows (silvr-cr-005); read-only, nothing is computed here."""

    data, problem, _ = _read_json_object(root / FORWARD_FILE)
    if problem == "missing":
        return [row("off", "status", "not started: no forward_progress.json yet")]
    if data is None:
        return [row("err", "status", f"unreadable: {problem}")]
    if data.get("kind") != "forward_progress":
        return [row("err", "status", "unreadable: kind is not forward_progress")]
    stored = data.get("status")
    if not isinstance(stored, str) or not stored:
        return [row("err", "status", "unreadable: status missing")]
    state = "ok" if stored in FORWARD_OK else "warn" if stored == "incomplete data" else "err"
    reason = data.get("reason")
    decided = stored in FORWARD_DECIDED or stored.startswith(("ended:", "void:"))
    note = data.get("note")
    gaps = data.get("data_gaps")
    # A void status already names its reason ("void: X" with reason "X"); say it once.
    shown = f"{stored}; {reason}" if isinstance(reason, str) and reason and reason not in stored else stored
    return [
        row(state, "status", shown),
        row("plain", "period", _forward_period(data)),
        row("plain", "net", _figure(data.get("net"), _money)),
        row("plain", "max drawdown", _figure(data.get("max_drawdown"), _money)),
        row("plain", "weekly average", _forward_weekly(data)),
        row("plain", "losing weeks", _figure(data.get("losing_week_share"), lambda share: f"{share * 100:.0f}%")),
        row("plain", "trades", _figure(data.get("trades"), str, whole=True)),
        row("plain", "kill switch trips", _figure(data.get("kill_switch_trips"), str, whole=True)),
        row("plain", "data gaps", ("; ".join(map(str, gaps)) or "none") if isinstance(gaps, list) else NOT_AVAILABLE),
        row("plain", "verdict date", VERDICT_DATE),
        # A verdict, an ended state or void must not sit beside "No verdict until ..." (V-2).
        row("plain", "NOTE", stored if decided else note if isinstance(note, str) and note else FORWARD_NOTE),
    ]


def _is_number(value: Any, *, whole: bool = False) -> bool:
    kind = int if whole else (int, float)
    return not isinstance(value, bool) and isinstance(value, kind) and math.isfinite(value)


def _figure(value: Any, show: Callable[[Any], str], *, whole: bool = False, missing: str = NOT_AVAILABLE) -> str:
    """A stored figure as text; anything missing or of the wrong type is "not available", never zero."""

    return show(value) if _is_number(value, whole=whole) else missing


def _money(amount: float) -> str:
    return f"{'-' if amount < 0 else ''}${abs(amount):.2f}"


def _forward_period(data: dict[str, Any]) -> str:
    done = data.get("days_done")
    try:
        through = _parse_time(data.get("through")).astimezone(UTC).date().isoformat()
    except ValueError:
        return NOT_AVAILABLE
    if not _is_number(done, whole=True):
        return NOT_AVAILABLE
    return f"{FORWARD_START} to {through}, {done} / {FORWARD_DAYS} days"


def _forward_weekly(data: dict[str, Any]) -> str:
    return _weekly_text(data.get("weekly_average"), data.get("weekly_target"), NOT_AVAILABLE)


def _weekly_text(average: Any, target: Any, missing: str) -> str:
    if not (_is_number(average) and _is_number(target)):
        return missing
    return f"{_money(average)} vs ${_number(target)} target"


def _analytics(root: Path) -> list[Row]:
    """The counted gate run as rows (silvr-cr-006); read-only, no maths beyond formatting.

    Rows with a ``kind`` key carry structured values for the renderer: ``criterion``,
    ``segment`` (one metric across the three segments) and ``bar`` (weekly net against target).
    Every row still reads as plain label, state and text, which is the fallback table.
    """

    folder = root / ANALYTICS_DIR
    rows = [*_gate_rows(folder / GATE_FILE), *_segment_rows(folder / VALIDATION_FILE)]
    if all(item["state"] == "off" for item in rows):
        return rows  # nothing to explain yet, like the forward panel before its first run
    return [*rows, row("plain", "NOTE", ANALYTICS_NOTE)]


def _gate_rows(path: Path) -> list[Row]:
    data, problem, _ = _read_json_object(path)
    if problem == "missing":
        return [row("off", "gate", f"not available: no {path.name} yet")]
    if data is None:
        return [row("err", "gate", f"unreadable: {problem}")]
    passed, criteria = data.get("passed"), data.get("criteria")
    if not isinstance(passed, bool):
        return [row("err", "gate", "unreadable: passed is not true or false")]
    if not isinstance(criteria, list) or not criteria:
        return [row("err", "gate", "unreadable: criteria missing")]
    shown = [_criterion(item) for item in criteria]
    cleared = sum(1 for item in shown if item.get("result") == "PASS")
    info = data.get("info")
    info = info if isinstance(info, dict) else {}
    start, end = _date(info.get("data_start")), _date(info.get("data_end"))
    bar = data.get("t_stat_bar")
    detail = [
        f"{cleared} of {len(shown)} criteria passed",
        f"t-bar {float(bar)}" if _is_number(bar) else f"t-bar {NA}",
        f"data {start} to {end}" if start and end else f"data range {NA}",
    ]
    verdict = row("ok" if passed else "err", "verdict", "; ".join(["GATE PASS" if passed else "GATE FAIL", *detail]))
    return [verdict, *shown]


def _criterion(item: Any) -> Row:
    if not isinstance(item, dict):
        return row("err", "criterion", "unreadable: not an object")
    number, name = item.get("number"), item.get("name")
    parts = [str(number)] if _is_number(number, whole=True) else []
    parts += [name] if isinstance(name, str) and name else []
    label = " ".join(parts) or "criterion"
    threshold, actual = _stored_text(item.get("threshold")), _stored_text(item.get("actual"))
    result = item.get("result")
    if result not in ("PASS", "FAIL"):
        result = NA  # an unreadable result is never counted as a pass
    return {
        **row("ok" if result == "PASS" else "err", label, f"threshold {threshold}; actual {actual}"),
        "kind": "criterion",
        "result": result,
        "threshold": threshold,
        "actual": actual,
    }


def _stored_text(value: Any) -> str:
    if isinstance(value, str) and value:
        return value
    return _number(value) if _is_number(value) else NA


def _date(value: Any) -> str:
    """The date part of a stored timestamp, or "" when it cannot be read."""

    try:
        return _parse_time(value).astimezone(UTC).date().isoformat()
    except ValueError:
        return ""


def _segment_rows(path: Path) -> list[Row]:
    data, problem, _ = _read_json_object(path)
    if problem == "missing":
        return [row("off", "segments", f"not available: no {path.name} yet")]
    if data is None:
        return [row("err", "segments", f"unreadable: {problem}")]
    segments = data.get("segments")
    if not isinstance(segments, dict):
        return [row("err", "segments", "unreadable: segments missing")]
    found = [segments.get(key) for key, _ in SEGMENTS]
    rows = [
        row("off", label.lower(), f"not available: no {key} segment in {path.name}")
        for (key, label), segment in zip(SEGMENTS, found)
        if not isinstance(segment, dict)
    ]
    columns = [_segment_cells(segment if isinstance(segment, dict) else {}) for segment in found]
    for index, metric in enumerate(SEGMENT_METRICS):
        cells = [column[index] for column in columns]
        text = "; ".join(f"{label.lower()} {cell}" for (_, label), cell in zip(SEGMENTS, cells))
        rows.append({**row("plain", metric, text), "kind": "segment", "cells": cells})
    for (_, label), segment, column in zip(SEGMENTS, found, columns):
        standard = segment.get("success_standard") if isinstance(segment, dict) else None
        standard = standard if isinstance(standard, dict) else {}
        average, target = standard.get("average_weekly_net"), standard.get("target_weekly_net")
        rows.append(
            {
                **row("plain", f"{label} weekly net", column[WEEKLY_METRIC]),
                "kind": "bar",
                "name": label,
                "value": average if _is_number(average) else None,
                "target": target if _is_number(target) else None,
            }
        )
    return rows


def _segment_cells(segment: dict[str, Any]) -> list[str]:
    """One segment's figures in SEGMENT_METRICS order; each missing or mistyped number is "not available"."""

    def part(name: str) -> dict[str, Any]:
        found = segment.get(name)
        return found if isinstance(found, dict) else {}

    metrics, standard, kill = part("metrics"), part("success_standard"), part("kill_switch")
    fees, funding = metrics.get("total_fees"), metrics.get("total_funding")
    weeks = standard.get("weeks")
    return [
        _period(segment),
        _figure(metrics.get("total_trades"), str, whole=True, missing=NA),
        _figure(metrics.get("net_profit"), _money, missing=NA),
        _figure(metrics.get("return_percent"), _percent, missing=NA),
        _figure(metrics.get("profit_factor"), lambda value: f"{value:.2f}", missing=NA),
        _figure(metrics.get("average_r"), lambda value: f"{value:.3f}", missing=NA),
        _figure(metrics.get("win_rate"), _percent, missing=NA),
        _figure(metrics.get("max_drawdown"), _money, missing=NA),
        _figure(metrics.get("max_drawdown_percent"), _percent, missing=NA),
        _money(fees + funding) if _is_number(fees) and _is_number(funding) else NA,
        _weekly_text(standard.get("average_weekly_net"), standard.get("target_weekly_net"), NA),
        _figure(
            standard.get("losing_week_share"),
            lambda share: f"{share * 100:.0f}%" + (f" of {weeks} weeks" if _is_number(weeks, whole=True) else ""),
            missing=NA,
        ),
        _figure(kill.get("trips"), str, whole=True, missing=NA),
    ]


def _percent(fraction: float) -> str:
    """A stored fraction (-0.012) as a percent (-1.2%)."""

    return f"{fraction * 100:.1f}%"


def _period(segment: dict[str, Any]) -> str:
    start, end = _date(segment.get("start")), _date(segment.get("end"))
    return f"{start} to {end}" if start and end else NA


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
