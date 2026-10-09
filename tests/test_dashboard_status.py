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
