import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg

from conftest import execute
from silvr.config import AppConfig, ConfigError
from silvr.monitoring.status import (
    AUDIT_EVENTS,
    AUDIT_TAIL_BYTES,
    EVIDENCE_REPORTS,
    PANEL_TITLES,
    _read_json_object,
    collect_status,
)
from silvr.storage import PostgresStorage

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
BANNER, READINESS, EVIDENCE, RISK, POSITIONS, ALERTS = range(6)


def make_config(root: Path, **overrides) -> AppConfig:
    return AppConfig(**overrides)


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
            "2026-10-09T07:24:18.217178+00:00",
            [
                {"name": "backtest_report_exists", "passed": True, "reason": "ok"},
                {"name": "paper_report_non_empty", "passed": False, "reason": "file is empty"},
            ],
        ),
    )
    write_report(tmp_path, "demo_readiness_report", readiness(True, "2026-10-09T10:31:00+00:00"))

    result = rows(collect(tmp_path), READINESS)

    assert result[0] == {"state": "err", "label": "live", "text": "NOT READY"}
    assert result[1] == {"state": "plain", "label": "", "text": "generated 2026-10-09 07:24 UTC"}
    assert result[2] == {"state": "err", "label": "", "text": "paper_report_non_empty: file is empty"}
    assert result[3] == {"state": "ok", "label": "demo", "text": "READY"}
    assert len(result) == 5


def test_readiness_is_stale_when_strategy_evidence_is_newer(tmp_path):
    generated = datetime(2026, 10, 9, 7, 24, tzinfo=UTC)
    write_report(tmp_path, "live_readiness_report", readiness(True, generated.isoformat()))
    write_report(tmp_path, "backtest_report", "{}", mtime=generated.timestamp() + 60)

    result = rows(collect(tmp_path), READINESS)

    assert result[0] == {"state": "warn", "label": "live", "text": "READY · stale"}
    assert result[1]["state"] == "warn"
    assert result[1]["text"].endswith("stale: evidence changed after this report")


def test_readiness_ready_older_than_24_hours_is_stale(tmp_path):
    generated = NOW - timedelta(hours=25)
    write_report(tmp_path, "live_readiness_report", readiness(True, generated.isoformat()))

    result = rows(collect(tmp_path), READINESS)

    assert result[0] == {"state": "warn", "label": "live", "text": "READY · stale"}
    assert result[1]["state"] == "warn"
    assert "older than 24 hours" in result[1]["text"]


def test_readiness_ready_within_24_hours_is_fresh(tmp_path):
    generated = NOW - timedelta(hours=23)
    write_report(tmp_path, "live_readiness_report", readiness(True, generated.isoformat()))

    result = rows(collect(tmp_path), READINESS)

    assert result[0] == {"state": "ok", "label": "live", "text": "READY"}
    assert result[1] == {"state": "plain", "label": "", "text": "generated 2026-10-08 13:00 UTC"}


def test_readiness_not_ready_older_than_24_hours_keeps_err_and_gains_stale(tmp_path):
    generated = NOW - timedelta(hours=25)
    write_report(tmp_path, "live_readiness_report", readiness(False, generated.isoformat()))

    result = rows(collect(tmp_path), READINESS)

    assert result[0] == {"state": "err", "label": "live", "text": "NOT READY · stale"}
    assert "older than 24 hours" in result[1]["text"]


def test_readiness_both_stale_reasons_are_listed_in_order(tmp_path):
    generated = NOW - timedelta(hours=30)
    write_report(tmp_path, "live_readiness_report", readiness(True, generated.isoformat()))
    write_report(tmp_path, "backtest_report", "{}", mtime=generated.timestamp() + 60)

    result = rows(collect(tmp_path), READINESS)

    assert result[1]["text"].endswith("stale: evidence changed after this report; older than 24 hours")


def test_readiness_tolerates_malformed_fields(tmp_path):
    write_report(tmp_path, "live_readiness_report", json.dumps({"ready": True, "checks": "oops"}))
    write_report(tmp_path, "demo_readiness_report", b"")

    result = rows(collect(tmp_path), READINESS)

    assert result[0] == {"state": "warn", "label": "live", "text": "READY · stale"}
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


STEP_STEMS = ("backtest_report", "out_of_sample_validation_report", "paper_trading_report")
STEP_LABELS = ("Backtest", "Out-of-sample", "Paper", "Demo", "Live")


def steps(status: dict) -> list[dict]:
    return status["ladder"]["steps"]


def fresh_demo(root: Path, ready: bool = True, hours: float = 1) -> None:
    generated = NOW - timedelta(hours=hours)
    write_report(root, "demo_readiness_report", readiness(ready, generated.isoformat()))


def old_mtime() -> float:
    return (NOW - timedelta(hours=40)).timestamp()


def test_ladder_has_five_labelled_steps_and_no_degraded_when_clean(tmp_path):
    status = collect(tmp_path)

    assert [item["label"] for item in steps(status)] == list(STEP_LABELS)
    assert status["degraded"] == 0


def test_ladder_strategy_steps_by_evidence_state(tmp_path):
    for index, stem in enumerate(STEP_STEMS):
        assert steps(collect(tmp_path))[index] == {"state": "off", "label": STEP_LABELS[index], "text": "missing"}
        write_report(tmp_path, stem, b"")
        assert steps(collect(tmp_path))[index] == {"state": "err", "label": STEP_LABELS[index], "text": "0 B"}
        write_report(tmp_path, stem, "not json")
        assert steps(collect(tmp_path))[index] == {"state": "err", "label": STEP_LABELS[index], "text": "8 B"}
        write_report(tmp_path, stem, "[1]")
        assert steps(collect(tmp_path))[index] == {"state": "err", "label": STEP_LABELS[index], "text": "3 B"}
        write_report(tmp_path, stem, "{}")
        assert steps(collect(tmp_path))[index] == {"state": "ok", "label": STEP_LABELS[index], "text": "2 B"}


def test_ladder_demo_fresh_is_ready(tmp_path):
    fresh_demo(tmp_path)

    assert steps(collect(tmp_path))[3] == {"state": "ok", "label": "Demo", "text": "READY"}


def test_ladder_demo_stale_is_ready_stale(tmp_path):
    fresh_demo(tmp_path, hours=25)

    assert steps(collect(tmp_path))[3] == {"state": "warn", "label": "Demo", "text": "READY · stale"}


def test_ladder_demo_not_ready_keeps_err_and_the_stale_suffix(tmp_path):
    fresh_demo(tmp_path, ready=False)
    assert steps(collect(tmp_path))[3] == {"state": "err", "label": "Demo", "text": "NOT READY"}
    fresh_demo(tmp_path, ready=False, hours=30)
    assert steps(collect(tmp_path))[3] == {"state": "err", "label": "Demo", "text": "NOT READY · stale"}


def test_ladder_demo_missing_is_off_and_bad_files_are_unreadable(tmp_path):
    assert steps(collect(tmp_path))[3] == {"state": "off", "label": "Demo", "text": "missing"}
    for content in (b"", "not json", "[]"):
        write_report(tmp_path, "demo_readiness_report", content)
        assert steps(collect(tmp_path))[3] == {"state": "err", "label": "Demo", "text": "unreadable"}


def test_ladder_live_is_blocked_even_when_live_report_says_ready(tmp_path):
    write_report(tmp_path, "live_readiness_report", readiness(True, (NOW - timedelta(hours=1)).isoformat()))

    assert steps(collect(tmp_path))[4] == {"state": "off", "label": "Live", "text": "blocked (PRD-F12)"}


def test_next_is_first_non_ok_step_with_exact_strip_text(tmp_path):
    from silvr.monitoring.status import ALL_GATES_PASS, NEXT_TEXT

    backtest = "Next: run a backtest (runbook-backtest.md steps 5 and 6)"
    paper = "Next: paper trading (not available yet, G-3)"
    demo = "Next: refresh demo readiness  python -m silvr.demo_readiness (runbook-demo-testnet.md steps 3 and 4)"
    assert NEXT_TEXT == (backtest, backtest, paper, demo)
    assert ALL_GATES_PASS == "All evidence gates pass. Live trading stays blocked (PRD-F12)."

    assert collect(tmp_path)["ladder"]["next"] == 0
    assert collect(tmp_path)["ladder"]["next_text"] == backtest

    write_report(tmp_path, STEP_STEMS[0], "{}", mtime=old_mtime())
    ladder = collect(tmp_path)["ladder"]
    assert (ladder["next"], ladder["next_text"]) == (1, backtest)

    write_report(tmp_path, STEP_STEMS[1], "{}", mtime=old_mtime())
    ladder = collect(tmp_path)["ladder"]
    assert (ladder["next"], ladder["next_text"]) == (2, paper)

    write_report(tmp_path, STEP_STEMS[2], "{}", mtime=old_mtime())
    ladder = collect(tmp_path)["ladder"]
    assert (ladder["next"], ladder["next_text"]) == (3, demo)

    fresh_demo(tmp_path, hours=25)
    assert collect(tmp_path)["ladder"]["next"] == 3

    fresh_demo(tmp_path)
    ladder = collect(tmp_path)["ladder"]
    assert (ladder["next"], ladder["next_text"]) == (None, ALL_GATES_PASS)


def test_next_skips_an_ok_step_after_a_failing_one(tmp_path):
    write_report(tmp_path, STEP_STEMS[2], "{}", mtime=old_mtime())
    fresh_demo(tmp_path)

    assert collect(tmp_path)["ladder"]["next"] == 0


def test_raising_collector_counts_as_degraded(tmp_path):
    (tmp_path / "logs" / "audit.jsonl").mkdir(parents=True)

    status = collect(tmp_path)

    assert status["degraded"] == 1
    assert len(steps(status)) == 5


def test_broken_panel_makes_ladder_unreadable_and_counts_both(tmp_path):
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "backtest_report.json").mkdir()

    status = collect(tmp_path)

    assert status["ladder"] == {
        "steps": [{"state": "err", "label": "unreadable", "text": "KeyError"}],
        "next": None,
        "next_text": "",
    }
    assert status["degraded"] == 2


def test_one_unreadable_source_only_breaks_its_panel(tmp_path):
    (tmp_path / "logs" / "audit.jsonl").mkdir(parents=True)

    status = collect(tmp_path)

    assert rows(status, ALERTS)[0]["state"] == "err"
    assert rows(status, ALERTS)[0]["label"] == "unreadable"
    for index in (BANNER, READINESS, EVIDENCE, RISK, POSITIONS):
        assert all(item["label"] != "unreadable" for item in rows(status, index))


def init_db(database_url: str) -> str:
    PostgresStorage(database_url).initialize()
    return database_url


def insert_risk_state(database_url: str, current_day: str) -> None:
    execute(
        database_url,
        "INSERT INTO risk_state VALUES (1, %s, %s, %s, %s, %s, %s)",
        (current_day, -12.5, 2, 3, 1, "2026-10-09T11:59:00+00:00"),
    )


def insert_paper_trade(database_url: str) -> None:
    execute(
        database_url,
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
        database_url,
        "INSERT INTO paper_events (event_type, symbol, timestamp, message, context_json) "
        "VALUES ('paper_trade_opened', 'BTCUSDT', '2026-10-09T10:00:00+00:00', 'opened', '{}')",
    )


def collect_db(root: Path, database_url: str, **overrides) -> dict:
    return collect(root, make_config(root, database_url=database_url, **overrides))


def test_database_panels_empty_when_no_database_configured(tmp_path):
    status = collect(tmp_path)

    assert rows(status, RISK) == [
        {"state": "off", "label": "", "text": "not available: risk_state empty, no running bot (G-3)"}
    ]
    assert rows(status, POSITIONS) == [{"state": "off", "label": "", "text": "none recorded (no paper run, G-3)"}]


def test_database_panels_empty_when_tables_missing(tmp_path, database_url):
    execute(database_url, "CREATE TABLE candles (id INTEGER PRIMARY KEY)")

    status = collect_db(tmp_path, database_url)

    assert rows(status, RISK)[0]["state"] == "off"
    assert rows(status, POSITIONS)[0]["text"] == "none recorded (no paper run, G-3)"


def test_unreachable_database_degrades_only_its_panels(tmp_path, fast_connect_timeout):
    status = collect_db(tmp_path, "postgresql://bot:pw@127.0.0.1:1/silvr?connect_timeout=2")

    assert rows(status, RISK)[0]["label"] == "unreadable"
    assert rows(status, POSITIONS)[0]["label"] == "unreadable"
    assert status["degraded"] == 2
    assert "bot:pw@" not in json.dumps(status)


def test_risk_budget_shows_row_and_limits(tmp_path, database_url):
    insert_risk_state(init_db(database_url), "2026-10-09")

    risk = by_label(collect_db(tmp_path, database_url), RISK)

    assert risk["day"] == {"state": "plain", "label": "day", "text": "2026-10-09"}
    assert risk["daily realized pnl"]["text"] == "-12.50"
    assert risk["trades today"]["text"] == "3"
    assert risk["consecutive losses"]["text"] == "2"
    assert risk["open positions"]["text"] == "1"
    assert risk["max daily loss"]["text"] == "0.02 of equity"
    assert risk["max risk per trade"]["text"] == "0.005 of equity"


def test_risk_budget_day_is_stale_when_not_today(tmp_path, database_url):
    insert_risk_state(init_db(database_url), "2026-10-08")

    risk = by_label(collect_db(tmp_path, database_url), RISK)

    assert risk["day"]["state"] == "warn"
    assert "stale" in risk["day"]["text"]


def test_positions_lists_simulated_trades_and_events(tmp_path, database_url):
    insert_risk_state(init_db(database_url), "2026-10-09")
    insert_paper_trade(database_url)

    result = rows(collect_db(tmp_path, database_url), POSITIONS)

    assert result[0] == {"state": "plain", "label": "open positions", "text": "1"}
    assert result[1]["label"].startswith("SIM ")
    assert result[1]["text"] == "BTCUSDT long 60000 to 60300, pnl 3.00, take_profit"
    assert result[2]["text"] == "paper_trade_opened: opened"


def test_collecting_writes_nothing_to_the_database(tmp_path, database_url):
    insert_risk_state(init_db(database_url), "2026-10-09")
    insert_paper_trade(database_url)
    snapshot = "SELECT (SELECT updated_at FROM risk_state), (SELECT count(*) FROM paper_trades), (SELECT count(*) FROM paper_events)"
    with psycopg.connect(database_url) as connection:
        before = connection.execute(snapshot).fetchone()

    collect_db(tmp_path, database_url)
    collect_db(tmp_path, database_url)

    with psycopg.connect(database_url) as connection:
        assert connection.execute(snapshot).fetchone() == before


def test_positions_show_stored_prices_exactly(tmp_path, database_url):
    insert_risk_state(init_db(database_url), "2026-10-09")
    insert_paper_trade(database_url)
    execute(database_url, "UPDATE paper_trades SET entry_price = %s, exit_price = %s", (64123.45, 120345.67))

    result = rows(collect_db(tmp_path, database_url), POSITIONS)

    assert result[1]["text"] == "BTCUSDT long 64123.45 to 120345.67, pnl 3.00, take_profit"


def test_risk_limits_show_stored_values_exactly(tmp_path, database_url):
    insert_risk_state(init_db(database_url), "2026-10-09")

    risk = by_label(collect_db(tmp_path, database_url, max_daily_loss=0.0123456789, max_risk_per_trade=0.005), RISK)

    assert risk["max daily loss"]["text"] == "0.0123456789 of equity"
    assert risk["max risk per trade"]["text"] == "0.005 of equity"


def test_positions_without_risk_state_row_is_not_available(tmp_path, database_url):
    insert_paper_trade(init_db(database_url))

    result = rows(collect_db(tmp_path, database_url), POSITIONS)

    assert result[0] == {"state": "off", "label": "open positions", "text": "not available: no risk_state row"}


def test_alerts_drop_line_the_bot_is_still_writing(tmp_path):
    path = write_audit(tmp_path, [audit_line("bot_started")])
    with path.open("ab") as handle:
        handle.write(b'{"event_type": "error", "mess')

    result = rows(collect(tmp_path), ALERTS)

    assert [item["text"] for item in result] == ["bot_started: m"]


def test_alerts_single_line_longer_than_tail_is_not_empty_log(tmp_path):
    write_audit(tmp_path, [audit_line("bot_started", "x" * (AUDIT_TAIL_BYTES + 10))])

    assert rows(collect(tmp_path), ALERTS) == [
        {"state": "off", "label": "", "text": "not available: no complete line in the last 64 KiB"}
    ]


def test_alerts_zero_byte_log_is_empty(tmp_path):
    path = tmp_path / "logs" / "audit.jsonl"
    path.parent.mkdir()
    path.write_bytes(b"")

    assert rows(collect(tmp_path), ALERTS) == [
        {"state": "off", "label": "", "text": "not available: audit log is empty"}
    ]


def test_read_json_object_returns_stat_from_the_same_open_file(tmp_path):
    assert _read_json_object(tmp_path / "none.json") == (None, "missing", None)
    path = write_report(tmp_path, "backtest_report", '{"a": 1}')

    data, problem, stat = _read_json_object(path)

    assert (data, problem) == ({"a": 1}, "")
    assert stat.st_size == 8
    _, problem, stat = _read_json_object(write_report(tmp_path, "empty", ""))
    assert (problem, stat.st_size) == ("empty", 0)


def test_risk_panel_reads_committed_row_while_a_writer_transaction_is_open(tmp_path, database_url):
    insert_risk_state(init_db(database_url), "2026-10-09")
    with psycopg.connect(database_url) as writer:
        writer.execute("UPDATE risk_state SET trades_today = 9")

        risk = by_label(collect_db(tmp_path, database_url), RISK)

        assert risk["trades today"]["text"] == "3"
        assert risk["daily realized pnl"]["text"] == "-12.50"
