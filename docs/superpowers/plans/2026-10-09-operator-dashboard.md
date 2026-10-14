# Operator Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build PRD-F13, a read-only status page on `127.0.0.1` that shows Silver Bot's mode, kill switch, readiness, risk state, paper activity, audit events and evidence-file health.

**Architecture:** Three units. `monitoring/status.py` reads six sources read-only into a plain dict of panels and rows. `render_page` in `monitoring/dashboard_server.py` turns that dict into escaped HTML with no I/O. `DashboardServer` in the same file serves `GET /` from a `ThreadingHTTPServer` bound to `127.0.0.1`. Each request collects and renders afresh; there is no script, polling or write path.

**Tech Stack:** Python 3.11+ standard library only (`http.server`, `sqlite3`, `json`, `html`, `string`, `argparse`); pytest for tests.

**Spec:** [docs/cr-silverbot-operator-dashboard.md](../../cr-silverbot-operator-dashboard.md) (`silverbot-cr-001`). Design system: [docs/dsd-silverbot.md](../../dsd-silverbot.md) sections 2 to 7 and 9.

## Global Constraints

- `pyproject.toml` keeps `dependencies = []`; import only the standard library and existing `silver_bot` modules.
- Bind address is the literal `127.0.0.1`; no `--host` option; default port `8765`.
- Only `GET /` returns 200. Other paths: 404. Other methods: 405 with `Allow: GET`. Foreign `Host` header: 400.
- Every response carries `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'`, `X-Content-Type-Options: nosniff`, `Cache-Control: no-store`, `Referrer-Policy: no-referrer`.
- SQLite is opened only as `file:<absolute path as URI>?mode=ro` with `uri=True`. The dashboard never writes any file; SQLite's own `-wal` and `-shm` sidecars are the only allowed side effect.
- `api_key`, `api_secret`, `telegram_bot_token` and `telegram_chat_id` are never read into the status dict or the page.
- State tags are exactly `[ OK ]`, `[ WRN ]`, `[ ERR ]`, `[ OFF ]` (DSD §2.2); every coloured state carries its tag and a word.
- Missing data reads `not available: <reason>` with the gap ID where one exists (DSD §4.1); nothing is estimated.
- Colours are the DSD §2.1 and §2.2 hex tokens; font stack `ui-monospace, "Cascadia Mono", Menlo, Consolas, monospace`; no web font, no script, no animation.
- Do not touch `main.py`, `src/silver_bot/main.py`, `src/silver_bot/config/**`, `risk/**`, `execution/**`, `exchange/**`, `data/**`, `readiness.py`, `demo_readiness.py`, Docker or `deploy/**`.
- Docs: no em dashes; no invented numbers; materialized files are regenerated with `python tools/materialize_docs.py`, never hand-edited.

## Review Focus

- A browser opened at `http://localhost:8765/` sends `Host: localhost:8765`; it must get the page, not 400 (Task 4 test `test_localhost_host_header_is_accepted`).
- The owner's working copy lives under a path with spaces (`C:\Users\Cian Jake Francisco\...`); the read-only SQLite URI must still open (Task 2 test `test_database_path_with_spaces_opens_read_only`).
- The real `logs/audit.jsonl` is already larger than 64 KiB; the tail read must drop the cut first line without counting it unreadable, and a non-UTF-8 line must count as unreadable rather than crash (Task 1 test `test_alerts_tail_of_large_log_drops_cut_line`).
- A readiness report with `checks` that is not a list, or no `generated_at`, must render a warning, not crash (Task 1 test `test_readiness_tolerates_malformed_fields`).
- Starting the dashboard while port 8765 is taken must print a clear message and exit 2, not a traceback (Task 4 test `test_main_exits_2_when_port_is_taken`).

---

### Task 0: Workspace

The worktree `.claude/worktrees/operator-dashboard` on branch `feat/operator-dashboard` (off `dev` at `e88f5c6`) already exists and holds the Change Record and this plan. All tasks run there. Another session (`silverbot-14`) works on `dev` in the main checkout `C:\SilverBot`; do not edit or commit there.

- [ ] **Step 1: Verify the baseline**

Run (in the worktree): `python -m pytest -q`
Expected: all tests pass (count printed, 0 failed).

- [ ] **Step 2: Commit the Change Record and plan**

```bash
git add docs/cr-silverbot-operator-dashboard.md docs/superpowers/plans/2026-10-09-operator-dashboard.md
git commit -m "docs: add operator dashboard Change Record and plan (silverbot-cr-001)"
```

---

### Task 1: File-backed panels (banner, readiness, evidence, alerts)

**Files:**
- Create: `src/silver_bot/monitoring/status.py`
- Test: `tests/test_dashboard_status.py`

**Interfaces:**
- Consumes: `silver_bot.config.AppConfig`, `ConfigError`, `load_config`; `silver_bot.monitoring.audit.redact_secrets`; `silver_bot.risk.kill_switch.KillSwitch(path).is_active() -> bool`.
- Produces:
  - `collect_status(root: str | Path, *, load: Callable[[], AppConfig] = load_config, now: datetime | None = None) -> dict` returning `{"generated_at": str, "panels": [{"title": str, "rows": [Row, ...]}, ...]}` with six panels in this order: `MODE & SAFETY`, `READINESS`, `EVIDENCE REPORTS`, `RISK BUDGET`, `OPEN POSITIONS / RECENT TRADES`, `ALERTS (logs/audit.jsonl)`.
  - `Row` is `{"state": "ok" | "warn" | "err" | "off" | "plain", "label": str, "text": str}`, built by `row(state, label, text="")`.
  - Module constants `PANEL_TITLES`, `EVIDENCE_REPORTS`, `AUDIT_TAIL_BYTES`, `AUDIT_EVENTS`, `RECENT_ROWS`, `NO_PAPER_RUN`.
  - Task 2 fills `_risk_budget` and `_positions`; in this task they are stubs that return the configuration-invalid or empty state so the six-panel shape is complete.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dashboard_status.py`:

```python
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from silver_bot.config import AppConfig, ConfigError
from silver_bot.monitoring.status import (
    AUDIT_EVENTS,
    AUDIT_TAIL_BYTES,
    EVIDENCE_REPORTS,
    PANEL_TITLES,
    collect_status,
)

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
BANNER, READINESS, EVIDENCE, RISK, POSITIONS, ALERTS = range(6)


def make_config(root: Path, **overrides) -> AppConfig:
    values = {"database_path": root / "data" / "silver_bot.sqlite3"}
    values.update(overrides)
    return AppConfig(**values)


def collect(root: Path, config: AppConfig | None = None) -> dict:
    chosen = config or make_config(root)
    return collect_status(root, load=lambda: chosen, now=NOW)


def rows(status: dict, index: int) -> list[dict]:
    return status["panels"][index]["rows"]


def by_label(status: dict, index: int) -> dict[str, dict]:
    return {item["label"]: item for item in rows(status, index)}


def write_report(root: Path, stem: str, content: str | bytes, mtime: float | None = None) -> Path:
    path = root / "reports" / f"{stem}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def readiness(ready: bool, generated_at: str, checks: list[dict] | None = None) -> str:
    return json.dumps({"ready": ready, "generated_at": generated_at, "checks": checks or []})


def write_audit(root: Path, lines: list[str | bytes]) -> Path:
    path = root / "logs" / "audit.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = b"".join((line.encode("utf-8") if isinstance(line, str) else line) + b"\n" for line in lines)
    path.write_bytes(data)
    return path


def audit_line(event_type: str, message: str = "m", **context) -> str:
    return json.dumps(
        {
            "context": context,
            "created_at": "2026-10-09T11:00:00+00:00",
            "event_type": event_type,
            "level": "INFO",
            "message": message,
        },
        sort_keys=True,
    )


def test_six_panels_in_layout_order(tmp_path):
    status = collect(tmp_path)

    assert [panel["title"] for panel in status["panels"]] == list(PANEL_TITLES)
    assert status["generated_at"] == "2026-10-09 12:00 UTC"


def test_banner_shows_mode_and_flags(tmp_path):
    banner = by_label(collect(tmp_path), BANNER)

    assert banner["MODE"] == {"state": "plain", "label": "MODE", "text": "PAPER"}
    assert banner["LIVE"]["state"] == "off"
    assert banner["PAPER"] == {"state": "ok", "label": "PAPER", "text": "ON"}
    assert banner["DEMO"]["state"] == "off"
    assert banner["KILL"] == {"state": "off", "label": "KILL", "text": "disabled"}


def test_kill_switch_states(tmp_path):
    no_path = by_label(collect(tmp_path, make_config(tmp_path, kill_switch_enabled=True)), BANNER)
    assert no_path["KILL"]["state"] == "warn"
    assert "path not set" in no_path["KILL"]["text"]

    switch = tmp_path / "run" / "KILL_SWITCH"
    armed = by_label(
        collect(tmp_path, make_config(tmp_path, kill_switch_enabled=True, kill_switch_path=switch)), BANNER
    )
    assert armed["KILL"]["state"] == "ok"

    switch.parent.mkdir()
    switch.write_text(json.dumps({"reason": "daily loss", "tripped_at": "2026-10-09T10:00:00+00:00"}))
    active = by_label(
        collect(tmp_path, make_config(tmp_path, kill_switch_enabled=True, kill_switch_path=switch)), BANNER
    )
    assert active["KILL"]["state"] == "err"
    assert active["KILL"]["text"].startswith("ACTIVE")
    assert "daily loss" in active["KILL"]["text"]
    assert switch.read_text() == json.dumps({"reason": "daily loss", "tripped_at": "2026-10-09T10:00:00+00:00"})


def test_rejected_config_shows_message_and_blocks_config_panels(tmp_path):
    def reject() -> AppConfig:
        raise ConfigError("PAPER_TRADING must be true when TRADING_MODE=paper")

    status = collect_status(tmp_path, load=reject, now=NOW)

    assert rows(status, BANNER) == [
        {"state": "err", "label": "CONFIG", "text": "config invalid: PAPER_TRADING must be true when TRADING_MODE=paper"}
    ]
    assert rows(status, RISK)[0]["state"] == "off"
    assert rows(status, POSITIONS)[0]["state"] == "off"


def test_evidence_rows_flag_missing_empty_and_invalid(tmp_path):
    write_report(tmp_path, "backtest_report", b"")
    write_report(tmp_path, "out_of_sample_validation_report", "not json")
    write_report(tmp_path, "paper_trading_report", "[1, 2]")
    write_report(tmp_path, "live_readiness_report", readiness(False, "2026-10-09T09:00:00+00:00"))

    evidence = by_label(collect(tmp_path), EVIDENCE)

    assert list(evidence) == list(EVIDENCE_REPORTS)
    assert evidence["backtest_report"]["state"] == "err"
    assert evidence["backtest_report"]["text"].startswith("0 B, modified ")
    assert evidence["backtest_report"]["text"].endswith("; empty")
    assert evidence["out_of_sample_validation_report"]["text"].endswith("; not valid JSON")
    assert evidence["paper_trading_report"]["text"].endswith("; not a JSON object")
    assert evidence["live_readiness_report"]["state"] == "ok"
    assert evidence["demo_readiness_report"] == {"state": "err", "label": "demo_readiness_report", "text": "missing"}


def test_readiness_ready_not_ready_and_failing_checks(tmp_path):
    write_report(
        tmp_path,
        "live_readiness_report",
        readiness(
            False,
            "2026-06-15T07:24:18.217178+00:00",
            [
                {"name": "backtest_report_exists", "passed": True, "reason": "ok"},
                {"name": "paper_report_non_empty", "passed": False, "reason": "file is empty"},
            ],
        ),
    )
    write_report(tmp_path, "demo_readiness_report", readiness(True, "2026-06-15T14:31:00+00:00"))

    result = rows(collect(tmp_path), READINESS)

    assert result[0] == {"state": "err", "label": "live", "text": "NOT READY"}
    assert result[1] == {"state": "plain", "label": "", "text": "generated 2026-06-15 07:24 UTC"}
    assert result[2] == {"state": "err", "label": "", "text": "paper_report_non_empty: file is empty"}
    assert result[3] == {"state": "ok", "label": "demo", "text": "READY"}
    assert len(result) == 5


def test_readiness_is_stale_when_strategy_evidence_is_newer(tmp_path):
    generated = datetime(2026, 6, 15, 7, 24, tzinfo=UTC)
    write_report(tmp_path, "live_readiness_report", readiness(True, generated.isoformat()))
    write_report(tmp_path, "backtest_report", "{}", mtime=generated.timestamp() + 60)

    result = rows(collect(tmp_path), READINESS)

    assert result[1]["state"] == "warn"
    assert "stale" in result[1]["text"]


def test_readiness_tolerates_malformed_fields(tmp_path):
    write_report(tmp_path, "live_readiness_report", json.dumps({"ready": True, "checks": "oops"}))
    write_report(tmp_path, "demo_readiness_report", b"")

    result = rows(collect(tmp_path), READINESS)

    assert result[0] == {"state": "ok", "label": "live", "text": "READY"}
    assert result[1] == {"state": "warn", "label": "", "text": "generated_at unreadable"}
    assert result[2] == {"state": "err", "label": "demo", "text": "empty"}


def test_alerts_tag_known_events_and_count_unreadable_lines(tmp_path):
    write_audit(
        tmp_path,
        [
            audit_line("bot_started"),
            audit_line("risk_rejected", "Max daily loss limit reached"),
            audit_line("error", "boom"),
            "not json",
            audit_line("mode_unavailable"),
        ],
    )

    result = rows(collect(tmp_path), ALERTS)

    assert [item["state"] for item in result] == ["ok", "warn", "err", "warn", "warn"]
    assert result[1]["label"] == "2026-10-09 11:00 UTC"
    assert result[1]["text"] == "risk_rejected: Max daily loss limit reached"
    assert result[-1] == {"state": "warn", "label": "", "text": "unreadable lines: 1"}


def test_alerts_tail_of_large_log_drops_cut_line(tmp_path):
    lines = [audit_line("bot_started", f"event {index:05d} " + "x" * 120) for index in range(1000)]
    lines.insert(990, b"\xff\xfe not utf-8")
    path = write_audit(tmp_path, lines)
    assert path.stat().st_size > AUDIT_TAIL_BYTES

    result = rows(collect(tmp_path), ALERTS)

    events = [item for item in result if item["label"]]
    assert len(events) == AUDIT_EVENTS
    assert events[-1]["text"].startswith("bot_started: event 00999")
    assert result[-1] == {"state": "warn", "label": "", "text": "unreadable lines: 1"}


def test_alerts_missing_log_is_not_available(tmp_path):
    assert rows(collect(tmp_path), ALERTS) == [
        {"state": "off", "label": "", "text": "not available: no audit log yet"}
    ]


def test_one_unreadable_source_only_breaks_its_panel(tmp_path):
    (tmp_path / "logs" / "audit.jsonl").mkdir(parents=True)

    status = collect(tmp_path)

    assert rows(status, ALERTS)[0]["state"] == "err"
    assert rows(status, ALERTS)[0]["label"] == "unreadable"
    for index in (BANNER, READINESS, EVIDENCE, RISK, POSITIONS):
        assert all(item["label"] != "unreadable" for item in rows(status, index))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_dashboard_status.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'silver_bot.monitoring.status'`.

- [ ] **Step 3: Write the implementation**

Create `src/silver_bot/monitoring/status.py`:

```python
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
    return [row("off", "", "not available: risk_state empty, no running bot (G-3)")]


def _positions(config: AppConfig | None, root: Path) -> list[Row]:
    if config is None:
        return [row("off", "", CONFIG_INVALID)]
    return [row("off", "", NO_PAPER_RUN)]


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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_dashboard_status.py -q`
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add src/silver_bot/monitoring/status.py tests/test_dashboard_status.py
git commit -m "feat(monitoring): collect read-only dashboard status from files (PRD-F13)"
```

---

### Task 2: SQLite panels (risk budget, positions and trades)

**Files:**
- Modify: `src/silver_bot/monitoring/status.py` (replace the `_risk_budget` and `_positions` stubs)
- Test: `tests/test_dashboard_status.py` (append)

**Interfaces:**
- Consumes: `_query(database: Path, sql: str) -> list[tuple] | None`, `_resolve`, `row`, `NO_PAPER_RUN`, `RECENT_ROWS` from Task 1; `silver_bot.storage.sqlite.SQLiteStorage(path).initialize()` in tests only.
- Produces: final `_risk_budget(config, root, now)` and `_positions(config, root)`; row labels `day`, `daily realized pnl`, `trades today`, `consecutive losses`, `open positions`, `updated`, `max daily loss`, `max risk per trade`, and `SIM <time>` rows.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dashboard_status.py`:

```python
import hashlib
import sqlite3

from silver_bot.storage.sqlite import SQLiteStorage


def init_db(path: Path) -> Path:
    SQLiteStorage(path).initialize()
    return path


def execute(path: Path, sql: str, params: tuple = ()) -> None:
    """Write test fixtures and close the connection, so WAL is checkpointed and no lock stays open."""

    connection = sqlite3.connect(path)
    try:
        with connection:
            connection.execute(sql, params)
    finally:
        connection.close()


def insert_risk_state(path: Path, current_day: str) -> None:
    # Column order: id, current_day, daily_realized_pnl, consecutive_losses, trades_today, open_positions, updated_at.
    execute(
        path,
        "INSERT OR REPLACE INTO risk_state VALUES (1, ?, ?, ?, ?, ?, ?)",
        (current_day, -12.5, 2, 3, 1, "2026-10-09T11:59:00+00:00"),
    )


def insert_paper_trade(path: Path) -> None:
    execute(
        path,
        """
        INSERT INTO paper_trades (
            trade_id, symbol, timeframe, session_name, direction, entry_time, exit_time,
            entry_price, exit_price, stop_loss, take_profit, position_size, risk_amount,
            realized_pnl, realized_r, fees, slippage, exit_reason, setup_quality_score, notes
        ) VALUES (1, 'BTCUSDT', '1m', 'ny_am', 'long', '2026-10-09T10:00:00+00:00',
                  '2026-10-09T10:30:00+00:00', 60000, 60300, 59800, 60400, 0.01, 2,
                  3, 1.5, 0.1, 0.05, 'take_profit', 80, '')
        """,
    )
    execute(
        path,
        "INSERT INTO paper_events (event_type, symbol, timestamp, message, context_json) "
        "VALUES ('paper_trade_opened', 'BTCUSDT', '2026-10-09T10:00:00+00:00', 'opened', '{}')",
    )


def digest(path: Path) -> tuple[str, int]:
    return hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns


def test_sqlite_panels_empty_when_database_missing(tmp_path):
    status = collect(tmp_path)

    assert rows(status, RISK) == [
        {"state": "off", "label": "", "text": "not available: risk_state empty, no running bot (G-3)"}
    ]
    assert rows(status, POSITIONS) == [{"state": "off", "label": "", "text": "none recorded (no paper run, G-3)"}]
    assert not (tmp_path / "data" / "silver_bot.sqlite3").exists()


def test_sqlite_panels_empty_when_tables_missing(tmp_path):
    database = tmp_path / "data" / "silver_bot.sqlite3"
    database.parent.mkdir()
    execute(database, "CREATE TABLE candles (id INTEGER PRIMARY KEY)")

    status = collect(tmp_path)

    assert rows(status, RISK)[0]["state"] == "off"
    assert rows(status, POSITIONS)[0]["text"] == "none recorded (no paper run, G-3)"


def test_risk_budget_shows_row_and_limits(tmp_path):
    database = init_db(tmp_path / "data" / "silver_bot.sqlite3")
    insert_risk_state(database, "2026-10-09")

    risk = by_label(collect(tmp_path), RISK)

    assert risk["day"] == {"state": "plain", "label": "day", "text": "2026-10-09"}
    assert risk["daily realized pnl"]["text"] == "-12.50"
    assert risk["trades today"]["text"] == "3"
    assert risk["consecutive losses"]["text"] == "2"
    assert risk["open positions"]["text"] == "1"
    assert risk["max daily loss"]["text"] == "0.02 of equity"
    assert risk["max risk per trade"]["text"] == "0.005 of equity"


def test_risk_budget_day_is_stale_when_not_today(tmp_path):
    database = init_db(tmp_path / "data" / "silver_bot.sqlite3")
    insert_risk_state(database, "2026-10-08")

    risk = by_label(collect(tmp_path), RISK)

    assert risk["day"]["state"] == "warn"
    assert "stale" in risk["day"]["text"]


def test_positions_lists_simulated_trades_and_events(tmp_path):
    database = init_db(tmp_path / "data" / "silver_bot.sqlite3")
    insert_risk_state(database, "2026-10-09")
    insert_paper_trade(database)

    result = rows(collect(tmp_path), POSITIONS)

    assert result[0] == {"state": "plain", "label": "open positions", "text": "1"}
    assert result[1]["label"].startswith("SIM ")
    assert result[1]["text"] == "BTCUSDT long 60000 to 60300, pnl 3.00, take_profit"
    assert result[2]["text"] == "paper_trade_opened: opened"


def test_database_path_with_spaces_opens_read_only(tmp_path):
    root = tmp_path / "dir with space"
    database = init_db(root / "data" / "silver_bot.sqlite3")
    insert_risk_state(database, "2026-10-09")

    risk = by_label(collect(root), RISK)

    assert risk["open positions"]["text"] == "1"


def test_collecting_leaves_database_bytes_unchanged(tmp_path):
    database = init_db(tmp_path / "data" / "silver_bot.sqlite3")
    insert_risk_state(database, "2026-10-09")
    insert_paper_trade(database)
    before = digest(database)

    collect(tmp_path)
    collect(tmp_path)

    assert digest(database) == before
    allowed = {database.name, database.name + "-wal", database.name + "-shm"}
    assert {path.name for path in database.parent.iterdir()} <= allowed
```

- [ ] **Step 2: Run the tests to verify the new ones fail**

Run: `python -m pytest tests/test_dashboard_status.py -q`
Expected: `test_risk_budget_shows_row_and_limits`, `test_risk_budget_day_is_stale_when_not_today`, `test_positions_lists_simulated_trades_and_events` and `test_database_path_with_spaces_opens_read_only` fail (KeyError or assertion on the stub rows); the rest pass.

- [ ] **Step 3: Replace the two stubs in `status.py`**

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_dashboard_status.py -q`
Expected: 19 passed.

- [ ] **Step 5: Commit**

```bash
git add src/silver_bot/monitoring/status.py tests/test_dashboard_status.py
git commit -m "feat(monitoring): read risk_state and paper tables read-only for the dashboard"
```

---

### Task 3: Page rendering

**Files:**
- Create: `src/silver_bot/monitoring/dashboard_server.py` (rendering part)
- Test: `tests/test_dashboard_server.py`

**Interfaces:**
- Consumes: the status dict from `collect_status` (Task 1 shape).
- Produces: `render_page(status: dict) -> str`; constants `TAGS`, `LAYOUT`, `SECURITY_HEADERS`, `BIND_HOST = "127.0.0.1"`, `DEFAULT_PORT = 8765` (Task 4 adds the server to this file).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dashboard_server.py`:

```python
import json
from datetime import UTC, datetime
from pathlib import Path

from silver_bot.config import AppConfig
from silver_bot.monitoring.dashboard_server import render_page
from silver_bot.monitoring.status import PANEL_TITLES, collect_status

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
SECRETS = {
    "api_key": "SENTINEL-KEY",
    "api_secret": "SENTINEL-SECRET",
    "telegram_bot_token": "SENTINEL-TOKEN",
    "telegram_chat_id": "SENTINEL-CHAT",
}


def make_config(root: Path, **overrides) -> AppConfig:
    values = {"database_path": root / "data" / "silver_bot.sqlite3"}
    values.update(overrides)
    return AppConfig(**values)


def write_audit(root: Path, *events: dict) -> None:
    path = root / "logs" / "audit.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(event, sort_keys=True) + "\n" for event in events), encoding="utf-8")


def page_for(root: Path, config: AppConfig | None = None) -> str:
    chosen = config or make_config(root)
    return render_page(collect_status(root, load=lambda: chosen, now=NOW))


def test_page_shows_six_panels_in_layout_order_with_banner_first(tmp_path):
    page = page_for(tmp_path)

    positions = [page.index(f"<caption>{title.replace('&', '&amp;')}</caption>") for title in PANEL_TITLES]
    assert positions == sorted(positions)
    assert page.index('class="row banner"') < positions[1]
    assert "<script" not in page
    assert "generated 2026-10-09 12:00 UTC" in page


def test_state_tags_carry_glyph_word_and_class(tmp_path):
    page = page_for(tmp_path)

    assert '<td class="off">[ OFF ]</td><td>OFF</td>' in page
    assert '<td class="ok">[ OK ]</td><td>ON</td>' in page
    assert '<td class="err">[ ERR ]</td><td>missing</td>' in page


def test_markup_in_sources_is_escaped(tmp_path):
    write_audit(
        tmp_path,
        {
            "context": {},
            "created_at": "2026-10-09T11:00:00+00:00",
            "event_type": "error",
            "level": "ERROR",
            "message": "<script>alert(1)</script>",
        },
    )

    page = page_for(tmp_path)

    assert "<script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


def test_secrets_never_reach_the_page(tmp_path):
    write_audit(
        tmp_path,
        {
            "context": {"api_key": "SENTINEL-KEY", "telegram_bot_token": "SENTINEL-TOKEN"},
            "created_at": "2026-10-09T11:00:00+00:00",
            "event_type": "bot_started",
            "level": "INFO",
            "message": "started",
        },
    )

    page = page_for(tmp_path, make_config(tmp_path, **SECRETS))

    for secret in SECRETS.values():
        assert secret not in page
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_dashboard_server.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'silver_bot.monitoring.dashboard_server'`.

- [ ] **Step 3: Write the rendering code**

Create `src/silver_bot/monitoring/dashboard_server.py`:

```python
"""Read-only operator dashboard on 127.0.0.1 (PRD-F13, silverbot-cr-001).

Run with ``python -m silver_bot.monitoring.dashboard_server [--port N]`` from the
project root. The page has no controls and the server answers GET only.
"""

from __future__ import annotations

import html
import string
from typing import Any

BIND_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
TAGS = {"ok": "[ OK ]", "warn": "[ WRN ]", "err": "[ ERR ]", "off": "[ OFF ]", "plain": ""}
# DSD section 3.2: banner; readiness | evidence; risk budget; positions | alerts.
LAYOUT: tuple[tuple[int, ...], ...] = ((0,), (1, 2), (3,), (4, 5))
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
}
CSS = """
:root{--canvas:#000000;--surface:#111827;--border:#374151;--ink:#F9FAFB;--muted:#9CA3AF;
--success:#10B981;--warning:#F59E0B;--danger:#EF4444}
*{box-sizing:border-box}
body{margin:0;background:var(--canvas);color:var(--ink);
font:14px/1.5 ui-monospace,"Cascadia Mono",Menlo,Consolas,monospace}
main{max-width:120ch;margin:0 auto;padding:1ch}
h1,caption{font-size:inherit;font-weight:bold;text-align:left}
h1{margin:0 0 1ch}
.row{display:flex;flex-wrap:wrap;gap:1ch;margin-bottom:1ch}
.banner{position:sticky;top:0;z-index:1;background:var(--canvas)}
section{flex:1 1 38ch;min-width:0;background:var(--surface);border:1px solid var(--border);padding:0 1ch}
table{width:100%;border-collapse:collapse}
th,td{padding:0 1ch 0 0;text-align:left;vertical-align:top;font-weight:normal}
thead th,th[scope=row],footer{color:var(--muted)}
td:last-child{overflow-wrap:anywhere}
td.ok,td.warn,td.err,td.off{white-space:nowrap}
.ok{color:var(--success)}.warn{color:var(--warning)}.err{color:var(--danger)}.off{color:var(--muted)}
"""
PAGE = string.Template(
    """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>silver-bot status</title>
<style>$css</style>
</head>
<body>
<main>
<h1>silver-bot status &middot; read-only &middot; 127.0.0.1</h1>
$panels
<footer>generated $generated_at &middot; read-only; reload to refresh</footer>
</main>
</body>
</html>
"""
)


def render_page(status: dict[str, Any]) -> str:
    """Render the status dict as one self-contained, escaped HTML page."""

    panels = status["panels"]
    groups = []
    for group in LAYOUT:
        css_class = "row banner" if group == LAYOUT[0] else "row"
        sections = "".join(_render_panel(panels[index]) for index in group)
        groups.append(f'<div class="{css_class}">{sections}</div>')
    return PAGE.substitute(css=CSS, panels="\n".join(groups), generated_at=html.escape(status["generated_at"]))


def _render_panel(panel: dict[str, Any]) -> str:
    body = "".join(
        f'<tr><th scope="row">{html.escape(item["label"])}</th>'
        f'<td class="{item["state"]}">{TAGS[item["state"]]}</td>'
        f'<td>{html.escape(item["text"])}</td></tr>'
        for item in panel["rows"]
    )
    return (
        f'<section><table><caption>{html.escape(panel["title"])}</caption>'
        '<thead><tr><th scope="col">item</th><th scope="col">state</th><th scope="col">detail</th></tr></thead>'
        f"<tbody>{body}</tbody></table></section>"
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_dashboard_server.py -q`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/silver_bot/monitoring/dashboard_server.py tests/test_dashboard_server.py
git commit -m "feat(monitoring): render dashboard status as escaped DSD-styled HTML"
```

---

### Task 4: Localhost server and entrypoint

**Files:**
- Modify: `src/silver_bot/monitoring/dashboard_server.py` (add imports, handler, server, `main`)
- Test: `tests/test_dashboard_server.py` (append)

**Interfaces:**
- Consumes: `render_page`, `BIND_HOST`, `DEFAULT_PORT`, `SECURITY_HEADERS` (Task 3); `collect_status(root, load=...)` (Task 1); `silver_bot.config.load_config`.
- Produces: `DashboardServer(port: int, *, root: Path, load: Callable[[], AppConfig] = load_config)` (a `ThreadingHTTPServer`), `DashboardHandler`, `main(argv: list[str] | None = None) -> int`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dashboard_server.py`:

```python
import hashlib
import http.client
import socket
import threading

import pytest

from silver_bot.monitoring.dashboard_server import BIND_HOST, DashboardServer, main
from silver_bot.storage.sqlite import SQLiteStorage


@pytest.fixture
def server(tmp_path):
    config = make_config(tmp_path)
    instance = DashboardServer(0, root=tmp_path, load=lambda: config)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    yield instance
    instance.shutdown()
    instance.server_close()


def call(server, method: str = "GET", path: str = "/", host: str | None = None):
    port = server.server_address[1]
    connection = http.client.HTTPConnection(BIND_HOST, port, timeout=5)
    connection.request(method, path, headers={"Host": host or f"127.0.0.1:{port}"})
    response = connection.getresponse()
    body = response.read().decode("utf-8")
    connection.close()
    return response, body


def test_get_root_returns_page_with_security_headers(server):
    response, body = call(server)

    assert response.status == 200
    assert response.getheader("Content-Type") == "text/html; charset=utf-8"
    assert response.getheader("Content-Security-Policy") == "default-src 'none'; style-src 'unsafe-inline'"
    assert response.getheader("X-Content-Type-Options") == "nosniff"
    assert response.getheader("Cache-Control") == "no-store"
    assert response.getheader("Referrer-Policy") == "no-referrer"
    assert "<caption>MODE &amp; SAFETY</caption>" in body


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def test_other_methods_get_405(server, method):
    response, _ = call(server, method)

    assert response.status == 405
    assert response.getheader("Allow") == "GET"


@pytest.mark.parametrize("path", ["/x", "/?a=1", "/favicon.ico"])
def test_unknown_paths_get_404(server, path):
    response, _ = call(server, path=path)

    assert response.status == 404


def test_foreign_host_header_gets_400(server):
    response, _ = call(server, host=f"evil.example:{server.server_address[1]}")

    assert response.status == 400


def test_localhost_host_header_is_accepted(server):
    response, _ = call(server, host=f"localhost:{server.server_address[1]}")

    assert response.status == 200


def test_server_binds_loopback_only(server):
    assert server.server_address[0] == "127.0.0.1"


def test_serving_changes_no_source_file(server, tmp_path):
    database = tmp_path / "data" / "silver_bot.sqlite3"
    SQLiteStorage(database).initialize()
    report = tmp_path / "reports" / "backtest_report.json"
    report.parent.mkdir()
    report.write_text("{}")
    write_audit(tmp_path, {"context": {}, "created_at": "2026-10-09T11:00:00+00:00",
                           "event_type": "bot_started", "level": "INFO", "message": "m"})
    tracked = [database, report, tmp_path / "logs" / "audit.jsonl"]
    before = {path: (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns) for path in tracked}
    files_before = {path for path in tmp_path.rglob("*")}

    for method in ("GET", "POST", "DELETE"):
        call(server, method)

    after = {path: (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns) for path in tracked}
    assert after == before
    new_files = {path.name for path in tmp_path.rglob("*")} - {path.name for path in files_before}
    assert new_files <= {database.name + "-wal", database.name + "-shm"}


def test_main_exits_2_when_port_is_taken(capsys):
    with socket.socket() as blocker:
        blocker.bind((BIND_HOST, 0))
        blocker.listen()
        port = blocker.getsockname()[1]

        assert main(["--port", str(port)]) == 2

    assert f"cannot listen on 127.0.0.1:{port}" in capsys.readouterr().err
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_dashboard_server.py -q`
Expected: ImportError, `cannot import name 'DashboardServer'`.

- [ ] **Step 3: Add the server to `dashboard_server.py`**

Replace the import block at the top of the file with:

```python
from __future__ import annotations

import argparse
import html
import string
import sys
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from silver_bot.config import AppConfig, load_config
from silver_bot.monitoring.status import collect_status
```

Append to the end of the file:

```python
class DashboardServer(ThreadingHTTPServer):
    """HTTP server fixed to 127.0.0.1 that serves the status page."""

    daemon_threads = True
    # On Windows SO_REUSEADDR lets a second socket share a busy port; refuse that.
    allow_reuse_address = sys.platform != "win32"

    def __init__(self, port: int, *, root: Path, load: Callable[[], AppConfig] = load_config) -> None:
        self.root = Path(root)
        self.load = load
        super().__init__((BIND_HOST, port), DashboardHandler)


class DashboardHandler(BaseHTTPRequestHandler):
    """Answer GET / with the page; refuse every other method, path and host."""

    server: DashboardServer
    server_version = "silver-bot-dashboard"
    sys_version = ""

    def parse_request(self) -> bool:
        if not super().parse_request():
            return False
        if self.command != "GET":
            self._send(405, "method not allowed\n", headers={"Allow": "GET"})
            return False
        return True

    def do_GET(self) -> None:
        if not self._host_allowed():
            self._send(400, "bad host\n")
            return
        if self.path != "/":
            self._send(404, "not found\n")
            return
        status = collect_status(self.server.root, load=self.server.load)
        self._send(200, render_page(status), content_type="text/html; charset=utf-8")

    def _host_allowed(self) -> bool:
        port = self.server.server_address[1]
        names = {"127.0.0.1", "localhost"}
        allowed = {f"{name}:{port}" for name in names} | (names if port == 80 else set())
        return self.headers.get("Host", "") in allowed

    def _send(
        self,
        code: int,
        body: str,
        *,
        content_type: str = "text/plain; charset=utf-8",
        headers: dict[str, str] | None = None,
    ) -> None:
        payload = body.encode("utf-8")
        self.send_response(code)
        for name, value in {
            "Content-Type": content_type,
            "Content-Length": str(len(payload)),
            **SECURITY_HEADERS,
            **(headers or {}),
        }.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)


def main(argv: list[str] | None = None) -> int:
    """Serve the read-only status page until interrupted."""

    parser = argparse.ArgumentParser(
        prog="python -m silver_bot.monitoring.dashboard_server",
        description="Read-only Silver Bot status page on 127.0.0.1.",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port on 127.0.0.1 (default {DEFAULT_PORT})")
    args = parser.parse_args(argv)
    try:
        server = DashboardServer(args.port, root=Path.cwd())
    except OSError as exc:
        print(f"cannot listen on {BIND_HOST}:{args.port}: {exc.strerror or exc}", file=sys.stderr)
        return 2
    print(f"silver-bot status: http://{BIND_HOST}:{server.server_address[1]}/ (read-only; Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_dashboard_server.py -q`
Expected: 18 passed (4 render tests, 1 GET, 5 methods, 3 paths, foreign host, localhost host, bind, no-change, port taken).

- [ ] **Step 5: Smoke-test against the real repository files**

`reports/`, `logs/` and `data/` are not tracked by git, so the real files exist only in the main checkout. Serve the worktree's code against them, read-only:
Run in one terminal, from `C:\SilverBot`: `PYTHONPATH=C:/SilverBot/.claude/worktrees/operator-dashboard/src python -m silver_bot.monitoring.dashboard_server --port 8765`
Run in another: `python -c "import urllib.request as u; r=u.urlopen('http://127.0.0.1:8765/'); print(r.status); b=r.read().decode(); print('[ ERR ]' in b, 'backtest_report' in b)"`
Expected: `200` then `True True` (the three 0-byte reports show `[ ERR ]`). Stop the server with Ctrl+C. Before and after, record `ls -l --time-style=full-iso reports logs data` in `C:\SilverBot` and confirm the sizes and times of `reports/*.json`, `logs/audit.jsonl` and `data/silver_bot.sqlite3` are unchanged.

- [ ] **Step 6: Run the full suite and commit**

Run: `python -m pytest -q`
Expected: all tests pass.

```bash
git add src/silver_bot/monitoring/dashboard_server.py tests/test_dashboard_server.py
git commit -m "feat(monitoring): serve the read-only dashboard on 127.0.0.1 (PRD-F13)"
```

---

### Task 5: Pre-merge review (SAD-A4)

**Files:**
- Modify: `docs/cr-silverbot-operator-dashboard.md` section 5

- [ ] **Step 1: Run restraint-guardian on the branch diff**

Spawn the `restraint-guardian` subagent with: "Review the diff `git diff dev...feat/operator-dashboard` for silverbot-cr-001 (docs/cr-silverbot-operator-dashboard.md). Report PASS or FAIL with file:line." The diff touches no live-gate surface and no risk, execution, exchange, config or readiness code, so SAD-A1 to SAD-A3 are not required (SAD section 4). Confirm that with `git diff --stat dev...feat/operator-dashboard`.

- [ ] **Step 2: Fix any FAIL finding**

For each FAIL, change the code, rerun `python -m pytest -q`, commit with a `fix(monitoring):` message, and rerun the reviewer until PASS or the owner records why a finding is accepted.

- [ ] **Step 3: Record the result**

In `docs/cr-silverbot-operator-dashboard.md` section 5, replace the row `| restraint-guardian (SAD-A4) | Open | Not yet run |` with the result, for example `| restraint-guardian (SAD-A4) | PASS | <one-line summary of the reviewer's notes> |` using the reviewer's actual words.

```bash
git add docs/cr-silverbot-operator-dashboard.md
git commit -m "docs: record restraint-guardian result for silverbot-cr-001"
```

---

### Task 6: Documentation updates (after silverbot-14's docs pass)

**Precondition:** `silverbot-14` has messaged that G-3 batch 2 is merged and its docs pass is committed on `dev`. Rebase first: `git rebase dev`, resolving conflicts by keeping both sides' rows. Then re-read each file below before editing, because batch 2 changes them.

**Files:**
- Modify: `docs/prd-silverbot.md`, `docs/dsd-silverbot.md`, `docs/sad-silverbot.md`, `docs/sdd-silverbot.md`, `docs/qad-silverbot.md`, `docs/ops-silverbot.md`, `docs/index.md`, `docs/log-silverbot.md`, `docs/cr-silverbot-operator-dashboard.md`
- Regenerate: `.claude/agents/psl-purist.md`, `BRAND.md`, `DESIGN.md` via `python tools/materialize_docs.py`

- [ ] **Step 1: PRD**

In `docs/prd-silverbot.md`:
- Section 3 table: add after the PRD-F12 row:
  `| PRD-F13 | Operator dashboard: read-only status page on localhost | Should | Built (caveats) | Six panels from files and SQLite, served on 127.0.0.1 (`monitoring/status.py`, `monitoring/dashboard_server.py`); panels 3 and 4 stay empty until a paper session runs (G-3) | [cr-silverbot-operator-dashboard.md](cr-silverbot-operator-dashboard.md) |`
- Section 4: add after the PRD-F11 block a `### PRD-F13 Operator dashboard` block holding US-23 and AC-23.1 to AC-23.7 copied from the Change Record section 3.1, each ending with `Test: tests/<file>::<test name>` from this plan (AC-23.1 `test_dashboard_server.py::test_page_shows_six_panels_in_layout_order_with_banner_first`; AC-23.2 `test_dashboard_server.py::test_serving_changes_no_source_file` and `::test_other_methods_get_405`; AC-23.3 `test_dashboard_status.py::test_evidence_rows_flag_missing_empty_and_invalid`; AC-23.4 `test_dashboard_server.py::test_secrets_never_reach_the_page`; AC-23.5 `test_dashboard_status.py::test_sqlite_panels_empty_when_database_missing`; AC-23.6 `test_dashboard_server.py::test_server_binds_loopback_only` and `::test_foreign_host_header_gets_400`; AC-23.7 `test_dashboard_status.py::test_one_unreadable_source_only_breaks_its_panel`).
- Update the story-count line after section 4 to the new total (current total plus one) and change "Each of PRD-F1 to PRD-F11" to include PRD-F13.
- Section 5.1 operator surface inventory: add a row for `python -m silver_bot.monitoring.dashboard_server [--port N]`, read-only status page on 127.0.0.1.

- [ ] **Step 2: DSD**

In `docs/dsd-silverbot.md`:
- Status line: `Draft (design system specified; mode A built per silverbot-cr-001)`.
- Banner paragraph: replace "The bot has no user interface today." with "Mode A, the read-only localhost dashboard, is built (PRD-F13, [cr-silverbot-operator-dashboard.md](cr-silverbot-operator-dashboard.md)); modes B and D are not." and change "Building any UI still needs the Change Record in §9.6." to "Building mode B or any other surface still needs its own Change Record (§9.6)."
- Section 1.2 surface-modes table: set mode A's status to `Built (PRD-F13)`.
- Section 9 heading: `## 9. Recommended UI (mode A approved and built; mode B proposal)`; at the end of §9.6 add: "Mode A was approved by [cr-silverbot-operator-dashboard.md](cr-silverbot-operator-dashboard.md) on 2026-10-09."
- Self-check: update the status-line item to the new status text.

- [ ] **Step 3: SAD and materialize**

In `docs/sad-silverbot.md` SAD-B1 card body, replace the sentence beginning "Gate first. Before writing any dashboard or terminal-view code" with:
"Gate first. The localhost dashboard (mode A) is approved as PRD-F13 by docs/cr-silverbot-operator-dashboard.md; change it only within that record's scope. Before writing terminal-view (mode B) or any other UI code, confirm the task cites an approved Change Record for it (docs/dsd-silverbot.md section 9.6). If it does not, stop and report "UI gate not met: DSD 9.6 needs an approved Change Record" and write nothing."
Add a line to the card's Toolbox paragraph: "Dashboard code lives in monitoring/status.py (collect) and monitoring/dashboard_server.py (render and serve); extend those rather than adding modules."
Then run: `python tools/materialize_docs.py` and `python tools/materialize_docs.py --check`
Expected: the second command prints `materialized: no changes`.

- [ ] **Step 4: SDD, QAD and OPS**

- `docs/sdd-silverbot.md` section 2 module map: next to the `monitoring/dashboard.py` entry, add `monitoring/status.py` (read-only status collection for PRD-F13) and `monitoring/dashboard_server.py` (HTML render and 127.0.0.1 server for PRD-F13).
- `docs/qad-silverbot.md` test register: add one row per AC-23.1 to AC-23.7 with the test names from Step 1, and the two new test files in the file inventory.
- `docs/ops-silverbot.md`: add a subsection "Operator dashboard" under the operator procedures: start command, URL `http://127.0.0.1:8765/`, that it is read-only and refreshes on reload, the meaning of `[ OK ]`, `[ WRN ]`, `[ ERR ]`, `[ OFF ]`, that the kill switch is still a file the owner creates or deletes, and that SQLite may create `-wal` and `-shm` files beside the database when the page reads it.

- [ ] **Step 5: Index, log and Change Record status**

- `docs/index.md`: replace "No Change Records yet. Records start once a doc is Locked." with "Change Records are listed in the table below and in section 1 under Change Records."; add a `### Change Records` table in section 1 with the row `| silverbot-cr-001 | [cr-silverbot-operator-dashboard.md](cr-silverbot-operator-dashboard.md) | Operator dashboard (PRD-F13) | Approved | 2026-10-09 |`; add PRD-F13 to the traceability matrix (`| PRD-F13 | Operator dashboard | Should | Built (caveats) | Yes | Yes | N/A |`); update the DSD row status to match Step 2; add this plan to Process records; add a section 2 row dated 2026-10-09 describing PRD-F13 with the test count from `python -m pytest -q`.
- `docs/log-silverbot.md`: append one row: date 2026-10-09, title "Operator dashboard", summary of what was built and the reviewer result, verification `python -m pytest -q`, `python tools/materialize_docs.py --check`.
- `docs/cr-silverbot-operator-dashboard.md`: status line `**Status:** Approved and built (2026-10-09)`; in section 3.1 keep the AC text unchanged.

- [ ] **Step 6: Verify and commit**

Run: `python -m pytest -q` and `python tools/materialize_docs.py --check` and `grep -rn "—" docs/cr-silverbot-operator-dashboard.md docs/prd-silverbot.md docs/dsd-silverbot.md docs/ops-silverbot.md`
Expected: all tests pass; `materialized: no changes`; the grep prints nothing.

```bash
git add docs .claude/agents BRAND.md DESIGN.md
git commit -m "docs: record PRD-F13 operator dashboard across the suite (silverbot-cr-001)"
```

---

### Task 7: Integrate into dev

- [ ] **Step 1: Coordinate**

Message `silverbot-14` that `feat/operator-dashboard` is ready to fast-forward into `dev`, and wait for its go-ahead (it may have a commit in flight).

- [ ] **Step 2: Rebase and verify**

In the worktree: `git rebase dev`, then `python -m pytest -q` and `python tools/materialize_docs.py --check`.
Expected: all pass, `materialized: no changes`.

- [ ] **Step 3: Fast-forward dev**

In the main checkout `C:\SilverBot` (clean tree, branch `dev`): `git merge --ff-only feat/operator-dashboard`, then `python -m pytest -q`.

- [ ] **Step 4: Clean up**

`git worktree remove .claude/worktrees/operator-dashboard` and `git branch -d feat/operator-dashboard`. Do not push; ask the owner first.
