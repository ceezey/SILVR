"""Phase 2 promotion gate: reads the out-of-sample report, prints PASS/FAIL, unlocks nothing."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from silvr.backtest import gate
from silvr.backtest.gate import GateInputError, evaluate_gate, main

FINAL_OK = {
    "total_trades": 120,
    "average_r": 0.30,
    "r_t_stat": 2.5,
    "profit_factor": 1.8,
    "realized_rr": 1.7,
    "max_drawdown_percent": 0.06,
    "return_percent": 0.30,
    "return_to_drawdown": 5.0,
    "average_win_r": 1.5,
    "average_loss_r": 1.0,
    "r_stdev": 1.0,
}
TRAINING_OK = {**FINAL_OK, "total_trades": 300, "average_r": 0.40}


def _segment(metrics: dict[str, Any] | None, candles: int, start: str, end: str, trips: int) -> dict[str, Any]:
    return {
        "candles": candles,
        "start": start,
        "end": end,
        "metrics": metrics,
        "kill_switch": {"mode": "simulated_per_run_daily_reset", "trips": trips, "trip_log": []},
    }


def report(
    final: dict[str, Any] | None | str = "default",
    training: dict[str, Any] | None | str = "default",
    **final_overrides: Any,
) -> dict[str, Any]:
    final_metrics = dict(FINAL_OK) if final == "default" else final
    if isinstance(final_metrics, dict):
        final_metrics.update(final_overrides)
    training_metrics = dict(TRAINING_OK) if training == "default" else training
    return {
        "method": "chronological_split",
        "fractions": {"training": 0.6, "validation": 0.2, "final_test": 0.2},
        "parameters_tuned": False,
        "segments": {
            "training": _segment(training_metrics, 6000, "2024-01-01T00:00:00+00:00", "2024-03-01T00:00:00+00:00", 1),
            "validation": _segment(
                copy.deepcopy(FINAL_OK), 2000, "2024-03-01T00:00:00+00:00", "2024-04-01T00:00:00+00:00", 0
            ),
            "final_test": _segment(final_metrics, 2000, "2024-04-01T00:00:00+00:00", "2024-05-01T00:00:00+00:00", 3),
        },
    }


def write_report(tmp_path: Path, data: Any) -> Path:
    path = tmp_path / "reports" / "out_of_sample_validation_report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


def run(tmp_path: Path, data: Any) -> tuple[int, Path]:
    path = write_report(tmp_path, data)
    return main(["--report", str(path)]), path


def failed_numbers(verdict) -> set[int]:
    return {c.number for c in verdict.criteria if c.result == "FAIL"}


def test_all_pass_exit_0_and_json_written(tmp_path, capsys):
    code, path = run(tmp_path, report())
    out = capsys.readouterr().out
    assert code == 0
    assert "GATE: PASS" in out
    assert "7  No peeking: strategy settings were frozen before this final test;" in out
    written = json.loads((path.parent / "promotion_gate.json").read_text(encoding="utf-8"))
    assert written["passed"] is True
    assert written["report"] == str(path)
    assert [c["number"] for c in written["criteria"]] == [1, 2, 3, 4, 5, 6]
    assert all(c["result"] == "PASS" for c in written["criteria"])
    assert "No peeking" in written["reminder"]


@pytest.mark.parametrize(
    ("overrides", "training", "expected"),
    [
        ({"total_trades": 99}, None, {1}),
        ({"average_r": 0.0}, None, {2, 6}),  # zero edge also fails the half-of-training bar
        ({"r_t_stat": 1.99}, None, {2}),
        ({"profit_factor": 1.49}, None, {3}),
        ({"realized_rr": 1.49}, None, {4}),
        ({"max_drawdown_percent": 0.11}, None, {5}),
        ({"return_to_drawdown": 1.99}, None, {5}),
        ({"average_r": 0.4 * 0.5 - 0.01}, None, {6}),
        ({}, {"average_r": 0.0}, {6}),
        ({}, {"average_r": -0.2}, {6}),
    ],
)
def test_single_failing_criterion(tmp_path, capsys, overrides, training, expected):
    training_metrics = {**TRAINING_OK, **training} if training is not None else "default"
    data = report(training=training_metrics, **overrides)
    assert failed_numbers(evaluate_gate(data)) == expected
    code, _ = run(tmp_path, data)
    assert code == 1
    assert "GATE: FAIL" in capsys.readouterr().out


def test_boundaries_pass():
    data = report(
        total_trades=100,
        r_t_stat=2.0,
        profit_factor=1.5,
        realized_rr=1.5,
        max_drawdown_percent=0.10,
        return_to_drawdown=2.0,
        average_r=0.2,
    )
    verdict = evaluate_gate(data)
    assert verdict.passed
    assert all(c.result == "PASS" for c in verdict.criteria)


def test_profit_factor_above_3_warns_but_passes(tmp_path, capsys):
    data = report(profit_factor=3.5)
    verdict = evaluate_gate(data)
    assert [c.result for c in verdict.criteria if c.number == 3] == ["WARN"]
    assert verdict.passed
    code, _ = run(tmp_path, data)
    out = capsys.readouterr().out
    assert code == 0
    assert "WARN" in out
    assert "GATE: PASS" in out


def test_inf_string_parsed(tmp_path):
    data = report(profit_factor="inf", realized_rr="inf", return_to_drawdown="inf")
    verdict = evaluate_gate(data)
    by_number = {c.number: c for c in verdict.criteria}
    assert by_number[3].result == "WARN"
    assert by_number[4].result == "PASS"
    assert by_number[5].result == "PASS"
    assert verdict.passed
    code, _ = run(tmp_path, data)
    assert code == 0


def test_zero_trades_fails_not_crashes(tmp_path, capsys):
    data = report(final=None)
    verdict = evaluate_gate(data)
    assert failed_numbers(verdict) == {1, 2, 3, 4, 5, 6}
    code, path = run(tmp_path, data)
    assert code == 1
    assert "GATE: FAIL" in capsys.readouterr().out
    assert json.loads((path.parent / "promotion_gate.json").read_text(encoding="utf-8"))["passed"] is False


def test_zero_trades_with_metrics_dict_fails():
    verdict = evaluate_gate(report(final={"total_trades": 0}))
    assert failed_numbers(verdict) == {1, 2, 3, 4, 5, 6}


def test_missing_training_metrics_fails_criterion_6_only():
    assert failed_numbers(evaluate_gate(report(training=None))) == {6}


def test_missing_or_malformed_report_exits_2(tmp_path, capsys):
    assert main(["--report", str(tmp_path / "nope.json")]) == 2
    assert run(tmp_path, "")[0] == 2
    assert run(tmp_path, "{}")[0] == 2
    assert run(tmp_path, "{not json")[0] == 2
    assert run(tmp_path, "[1, 2]")[0] == 2
    assert not (tmp_path / "reports" / "promotion_gate.json").exists()
    assert "re-run the backtest" in capsys.readouterr().err


def test_missing_segment_is_not_a_pass(tmp_path):
    data = report()
    del data["segments"]["final_test"]
    with pytest.raises(GateInputError):
        evaluate_gate(data)
    assert run(tmp_path, data)[0] == 2


def test_report_missing_new_metric_keys_exits_2(tmp_path, capsys):
    data = report()
    del data["segments"]["final_test"]["metrics"]["r_t_stat"]
    code, path = run(tmp_path, data)
    assert code == 2
    assert "re-run the backtest" in capsys.readouterr().err
    assert not (path.parent / "promotion_gate.json").exists()


def test_info_rows(tmp_path, capsys):
    code, path = run(tmp_path, report())
    out = capsys.readouterr().out
    assert code == 0
    assert "2024-01-01T00:00:00+00:00" in out
    assert "2024-05-01T00:00:00+00:00" in out
    assert "10000" in out  # 6000 + 2000 + 2000 candles
    written = json.loads((path.parent / "promotion_gate.json").read_text(encoding="utf-8"))
    assert written["info"] == {
        "data_start": "2024-01-01T00:00:00+00:00",
        "data_end": "2024-05-01T00:00:00+00:00",
        "candles": 10000,
        "final_test_kill_switch_trips": 3,
    }


def test_thresholds_are_module_constants():
    assert (gate.MIN_TRADES, gate.MIN_T_STAT, gate.MIN_PROFIT_FACTOR, gate.WARN_PROFIT_FACTOR) == (100, 2.0, 1.5, 3.0)
    assert (gate.MIN_REALIZED_RR, gate.MAX_DRAWDOWN_PERCENT) == (1.5, 0.10)
    assert (gate.MIN_RETURN_TO_DRAWDOWN, gate.MIN_OOS_EFFICIENCY) == (2.0, 0.5)


def test_repeat_bar_constant():
    assert gate.MIN_T_STAT_REPEAT == 3.0


def test_gate_does_not_touch_config_or_readiness(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = write_report(tmp_path, report())
    before = set(tmp_path.rglob("*"))
    assert main(["--report", str(path)]) == 0
    after = set(tmp_path.rglob("*"))
    assert after - before == {path.parent / "promotion_gate.json", path.parent / "promotion_gate_log.jsonl"}


def _log_lines(path: Path) -> list[dict[str, Any]]:
    text = (path.parent / "promotion_gate_log.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def test_each_run_appends_an_audit_line_and_counts_looks(tmp_path, capsys):
    code, path = run(tmp_path, report(r_t_stat=3.5))  # clears the repeat-look bar of 3.0
    assert code == 0
    assert "gate runs on this data range: 1" in capsys.readouterr().out

    assert main(["--report", str(path)]) == 0
    out = capsys.readouterr().out
    assert out.index("GATE: PASS") < out.index("gate runs on this data range: 2")

    lines = _log_lines(path)
    assert len(lines) == 2
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    for line in lines:
        assert set(line) == {
            "run_at",
            "report",
            "report_sha256",
            "data_start",
            "data_end",
            "candles",
            "passed",
            "strategy",
            "t_stat_bar",
        }
        assert line["report"] == str(path)
        assert line["report_sha256"] == digest
        assert line["data_start"] == "2024-01-01T00:00:00+00:00"
        assert line["data_end"] == "2024-05-01T00:00:00+00:00"
        assert line["candles"] == 10000
        assert line["passed"] is True
        assert datetime.fromisoformat(line["run_at"]).utcoffset() == timedelta(0)


def test_different_data_range_is_counted_separately(tmp_path, capsys):
    run(tmp_path, report(r_t_stat=3.5))
    run(tmp_path, report(r_t_stat=3.5))
    capsys.readouterr()

    other = report(r_t_stat=3.5)
    other["segments"]["final_test"]["end"] = "2024-06-01T00:00:00+00:00"
    code, path = run(tmp_path, other)

    assert code == 0
    assert "gate runs on this data range: 1" in capsys.readouterr().out
    assert len(_log_lines(path)) == 3

    assert main(["--report", str(path)]) == 0
    assert "gate runs on this data range: 2" in capsys.readouterr().out


def test_failing_run_is_logged_with_passed_false(tmp_path, capsys):
    code, path = run(tmp_path, report(total_trades=99))
    assert code == 1
    assert "gate runs on this data range: 1" in capsys.readouterr().out
    assert _log_lines(path)[0]["passed"] is False


def test_exit_2_paths_append_nothing(tmp_path, capsys):
    run(tmp_path, report())
    capsys.readouterr()
    log = tmp_path / "reports" / "promotion_gate_log.jsonl"
    before = log.read_bytes()

    assert main(["--report", str(tmp_path / "nope.json")]) == 2
    assert run(tmp_path, "{not json")[0] == 2
    assert run(tmp_path, "{}")[0] == 2

    assert log.read_bytes() == before
    assert "gate runs on this data range" not in capsys.readouterr().out


def _seed_log(tmp_path: Path, *lines: str) -> Path:
    log = tmp_path / "reports" / "promotion_gate_log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    return log


def _old_line(**overrides: Any) -> str:
    entry = {
        "run_at": "2026-10-21T09:39:08+00:00",
        "report": "reports/out_of_sample_validation_report.json",
        "report_sha256": "0" * 64,
        "data_start": "2024-01-01T00:00:00+00:00",
        "data_end": "2024-05-01T00:00:00+00:00",
        "candles": 10000,
        "passed": False,
    }
    return json.dumps({**entry, **overrides})


def _criterion(verdict, number: int):
    return next(c for c in verdict.criteria if c.number == number)


def test_first_look_bar_2(tmp_path, capsys):
    verdict = evaluate_gate(report(r_t_stat=2.0))
    assert verdict.passed
    assert verdict.t_stat_bar == 2.0
    assert "t >= 2.0" in _criterion(verdict, 2).threshold
    code, path = run(tmp_path, report(r_t_stat=2.5))
    assert code == 0
    assert "t-stat bar: 2.0 (look 1 at this data range, all strategies)" in capsys.readouterr().out


def test_second_look_bar_3_fails_t_2_5(tmp_path, capsys):
    verdict = evaluate_gate(report(r_t_stat=2.5), prior_looks=1)
    assert failed_numbers(verdict) == {2}
    assert "t >= 3.0" in _criterion(verdict, 2).threshold
    assert verdict.t_stat_bar == 3.0
    assert evaluate_gate(report(r_t_stat=3.0), prior_looks=1).passed

    assert run(tmp_path, report(r_t_stat=2.5))[0] == 0
    capsys.readouterr()
    code, path = run(tmp_path, report(r_t_stat=2.5))
    out = capsys.readouterr().out
    assert code == 1
    assert "t-stat bar: 3.0 (look 2 at this data range, all strategies)" in out
    assert "gate runs on this data range: 2" in out
    assert _log_lines(path)[-1]["passed"] is False


def test_looks_counted_across_strategies(tmp_path, capsys):
    data = report(r_t_stat=2.5)
    data["strategy"] = "other_strategy"
    _seed_log(tmp_path, _old_line(strategy="unnamed", t_stat_bar=2.0, passed=True))
    code, path = run(tmp_path, data)
    assert code == 1
    assert "look 2 at this data range" in capsys.readouterr().out
    # a different data range is a first look
    _seed_log(tmp_path, _old_line(data_end="2024-04-01T00:00:00+00:00"))
    assert main(["--report", str(path)]) == 0


def test_strategy_in_json_and_log(tmp_path):
    data = report()
    data["strategy"] = "other_strategy"
    code, path = run(tmp_path, data)
    assert code == 0
    written = json.loads((path.parent / "promotion_gate.json").read_text(encoding="utf-8"))
    assert (written["strategy"], written["t_stat_bar"]) == ("other_strategy", 2.0)
    assert (_log_lines(path)[0]["strategy"], _log_lines(path)[0]["t_stat_bar"]) == ("other_strategy", 2.0)

    # reports from before the strategy key existed are "unnamed"
    code, path = run(tmp_path, report(r_t_stat=3.5))
    line = _log_lines(path)[-1]
    assert (line["strategy"], line["t_stat_bar"]) == ("unnamed", 3.0)
    written = json.loads((path.parent / "promotion_gate.json").read_text(encoding="utf-8"))
    assert (written["strategy"], written["t_stat_bar"]) == ("unnamed", 3.0)


def test_existing_log_without_strategy_still_counts(tmp_path, capsys):
    _seed_log(tmp_path, _old_line())
    code, _ = run(tmp_path, report(r_t_stat=2.5))
    assert code == 1
    assert "look 2 at this data range" in capsys.readouterr().out


@pytest.mark.parametrize("bad", ["{not json", "[1, 2]", '"text"'])
def test_unparseable_log_line_fails_closed(tmp_path, capsys, bad):
    log = _seed_log(tmp_path, _old_line(), bad)
    before = log.read_bytes()
    code, path = run(tmp_path, report())
    assert code == 2
    assert "promotion_gate_log.jsonl" in capsys.readouterr().err
    assert log.read_bytes() == before
    assert not (path.parent / "promotion_gate.json").exists()


def test_trend_drawdown_limit_030():
    data = report(max_drawdown_percent=0.25)
    data["strategy"] = "trend_ensemble"
    verdict = evaluate_gate(data)
    assert 5 not in failed_numbers(verdict)
    assert "<= 0.3" in _criterion(verdict, 5).threshold
    data["strategy"] = "other_strategy"
    assert 5 in failed_numbers(evaluate_gate(data))
    assert gate.MAX_DRAWDOWN_PERCENT_BY_STRATEGY == {"trend_ensemble": 0.30}


def test_trend_drawdown_above_030_fails():
    data = report(max_drawdown_percent=0.31)
    data["strategy"] = "trend_ensemble"
    assert 5 in failed_numbers(evaluate_gate(data))


def test_default_drawdown_limit_unchanged():
    assert gate.MAX_DRAWDOWN_PERCENT == 0.10
    assert "<= 0.1" in _criterion(evaluate_gate(report()), 5).threshold


def test_skipped_final_test_is_input_error(tmp_path, capsys):
    data = report()
    data["segments"]["final_test"] = {"skipped": True}
    with pytest.raises(GateInputError, match="final_test"):
        evaluate_gate(data)
    code, _ = run(tmp_path, data)
    assert code == 2


def test_gate_refuses_forward_progress_report(tmp_path, capsys):
    """A monthly forward progress report is never a gate input: exit 2, nothing written or logged."""
    data = {**report(), "kind": "forward_progress"}
    with pytest.raises(GateInputError, match="forward progress report is not a gate input"):
        evaluate_gate(data)
    code, path = run(tmp_path, data)
    assert code == 2
    assert not (path.parent / gate.OUTPUT_NAME).exists()
    assert not (path.parent / gate.LOG_NAME).exists()
    assert "only the forward verdict report is" in capsys.readouterr().err


def test_gate_accepts_the_forward_verdict_report(tmp_path):
    code, _ = run(tmp_path, {**report(), "kind": "forward_verdict"})
    assert code == 0
