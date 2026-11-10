"""Tests for the trend_ensemble forward test: frozen-files check, fixed-window simulation, progress report."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Any

import pytest

from silvr.backtest import gate
from silvr.backtest.gate import LOG_NAME, OUTPUT_NAME, GateInputError, evaluate_gate
from silvr.backtest.reporting import json_safe
from silvr.backtest.trend_engine import TrendDataError
from silvr.backtest.trend_forward import (
    FORWARD_END,
    FORWARD_START,
    HISTORY_NAME,
    NOTE,
    ORIGINAL_FIRST,
    ORIGINAL_LAST,
    PROGRESS_NAME,
    VerdictRefused,
    backtest_config,
    check_frozen,
    head_commit,
    last_closed_minute,
    record_void,
    run_progress,
    run_verdict,
    simulate_window,
)
from silvr.backtest.trend_runner import REPORT_NAME, SEGMENT_NAMES, run_trend_backtest, segment_bounds
from silvr.risk import RiskConfig
from silvr.strategy.trend import params
from tests.test_trend_runner import DAYS, MINUTE, START, SYMBOLS, tiny_universe, write_data, write_month  # noqa: F401

PATHS = ("a.py", "pkg")


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, str]:
    """A throwaway git repo with one commit holding a.py and pkg/b.py; returns (root, commit)."""
    _git(tmp_path, "init", "-q")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "a.py").write_text("a = 1\n")
    (tmp_path / "pkg" / "b.py").write_text("b = 1\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path, _git(tmp_path, "rev-parse", "HEAD")


def test_check_frozen_clean_tree_is_frozen(repo: tuple[Path, str]) -> None:
    root, commit = repo
    assert check_frozen(root, commit=commit, paths=PATHS) == []


def test_check_frozen_reports_a_changed_file(repo: tuple[Path, str]) -> None:
    root, commit = repo
    (root / "a.py").write_text("a = 2\n")
    problems = check_frozen(root, commit=commit, paths=PATHS)
    assert len(problems) == 1
    assert "a.py" in problems[0]


def test_check_frozen_reports_an_untracked_file(repo: tuple[Path, str]) -> None:
    root, commit = repo
    (root / "pkg" / "c.py").write_text("c = 1\n")
    problems = check_frozen(root, commit=commit, paths=PATHS)
    assert len(problems) == 1
    assert "pkg/c.py" in problems[0]


def test_check_frozen_fails_closed_on_unknown_commit(repo: tuple[Path, str]) -> None:
    root, _ = repo
    assert check_frozen(root, commit="0" * 40, paths=PATHS) != []


def test_check_frozen_fails_closed_outside_git(tmp_path: Path) -> None:
    assert check_frozen(tmp_path, commit="0" * 40, paths=PATHS) != []


def test_repo_is_frozen_at_freeze_commit() -> None:
    """Tripwire: any edit to a frozen file on this branch fails it."""
    root = Path(__file__).parents[1]
    probe = subprocess.run(
        ["git", "rev-parse", "--git-dir"], cwd=root, capture_output=True, text=True
    )
    if probe.returncode != 0:
        pytest.skip("not a git checkout")
    assert check_frozen(root) == []


def test_last_closed_minute_from_manila_morning_on_the_first() -> None:
    now = datetime(2026, 12, 1, 1, 0, tzinfo=UTC)
    assert last_closed_minute(now) == datetime(2026, 11, 30, 23, 59, tzinfo=UTC)


def test_last_closed_minute_is_capped_at_forward_end() -> None:
    assert last_closed_minute(datetime(2028, 1, 1, tzinfo=UTC)) == FORWARD_END


def test_backtest_config_matches_the_frozen_runner() -> None:
    config = backtest_config()
    assert config.initial_balance == params.INITIAL_BALANCE
    assert config.risk == RiskConfig.trend()
    assert config.slippage_bps == 5.0
    assert config.spread_bps == 3.0


def test_simulate_window_rejects_data_ending_before_end(tiny_universe: None, tmp_path: Path) -> None:
    candles, funding = write_data(tmp_path)
    last = START + DAYS * 1440 * MINUTE - MINUTE
    with pytest.raises(TrendDataError, match="does not cover the window"):
        simulate_window(
            candles_root=candles, funding_root=funding, start=START, end=last + timedelta(days=1), k=1.0
        )


def test_simulate_window_rejects_data_starting_after_start(tiny_universe: None, tmp_path: Path) -> None:
    candles, funding = write_data(tmp_path)
    late = START + timedelta(days=1)
    for symbol in SYMBOLS:  # replace the month with one whose first candle is a day late
        write_month(candles / symbol / f"{symbol}-1m-2024-03.csv", late, (DAYS - 1) * 1440)
    with pytest.raises(TrendDataError, match="does not cover the window"):
        simulate_window(
            candles_root=candles, funding_root=funding, start=START, end=START + 5 * 1440 * MINUTE, k=1.0
        )


def test_simulate_window_matches_runner_segment(tiny_universe: None, tmp_path: Path) -> None:
    candles, funding = write_data(tmp_path)
    path = run_trend_backtest(
        candles_root=candles, funding_root=funding, output_dir=tmp_path / "out", segments=SEGMENT_NAMES, k=1.0
    )
    expected = json.loads(path.read_text(encoding="utf-8"))["segments"]["final_test"]
    start, end = segment_bounds(START, START + DAYS * 1440 * MINUTE - MINUTE)["final_test"]
    got = simulate_window(candles_root=candles, funding_root=funding, start=start, end=end, k=1.0)
    assert json.loads(json.dumps(json_safe(got))) == expected


def test_head_commit_returns_the_repo_commit(repo: tuple[Path, str]) -> None:
    root, commit = repo
    assert head_commit(root) == commit


DEC_1 = datetime(2026, 12, 1, 1, 0, tzinfo=UTC)
JAN_1 = datetime(2027, 1, 1, 1, 0, tzinfo=UTC)
FEB_1 = datetime(2027, 2, 1, 1, 0, tzinfo=UTC)
GAP = "BTCUSDT: no 1m candle at 2026-11-15T03:00:00+00:00 (month 2026-11)"


def _segment(trips: int = 0) -> dict[str, Any]:
    return {
        "metrics": {
            "net_profit": 12.5,
            "max_drawdown": 40.0,
            "total_fees": 3.0,
            "total_funding": -1.0,
            "total_trades": 4,
            "average_r": 0.1,
            "profit_factor": 1.2,
            "realized_rr": 1.1,
        },
        "kill_switch": {"trips": trips, "tripped_at": datetime(2026, 11, 20, 5, tzinfo=UTC) if trips else None},
        "success_standard": {
            "weeks": 3,
            "average_weekly_net": 4.0,
            "losing_week_share": 1 / 3,
            "worst_week": -2.0,
            "target_weekly_net": 50.0,
            "met": False,
        },
    }


class FakeSimulate:
    """Records each call; returns `segment`, or raises TrendDataError(`gap`) when `segment` is None."""

    def __init__(self, segment: dict[str, Any] | None = None, gap: str = GAP) -> None:
        self.segment = segment
        self.gap = gap
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.segment is None:
            error = TrendDataError("BTCUSDT", None)
            error.args = (self.gap,)
            raise error
        return self.segment


def _no_problems(_root: Path) -> list[str]:
    return []


def _run(
    root: Path, tmp_path: Path, now: datetime, simulate: FakeSimulate, check: Any = _no_problems, **extra: Any
) -> dict[str, Any] | None:
    return run_progress(
        repo_root=root,
        data_root=tmp_path / "data",
        output_dir=tmp_path / "out",
        now=now,
        simulate=simulate,
        check=check,
        **extra,
    )


def _history(tmp_path: Path) -> list[dict[str, Any]]:
    lines = (tmp_path / "out" / HISTORY_NAME).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def test_progress_running_writes_report_and_history(repo: tuple[Path, str], tmp_path: Path) -> None:
    root, commit = repo
    simulate = FakeSimulate(_segment())
    report = _run(root, tmp_path, DEC_1, simulate)
    assert report is not None
    assert report["status"] == "running"
    assert report["note"] == NOTE
    assert report["through"] == "2026-11-30T23:59:00+00:00"
    assert report["days_done"] == 20
    assert report["days_total"] == 365
    assert report["net"] == 12.5
    assert report["weekly_average"] == 4.0
    assert report["kill_switch_trips"] == 0
    assert report["data_gaps"] == []
    assert report["commits"] == [commit]
    assert report["frozen_check"] == "ok"
    assert simulate.calls == [
        {
            "candles_root": tmp_path / "data" / "candles",
            "funding_root": tmp_path / "data" / "funding",
            "start": FORWARD_START,
            "end": datetime(2026, 11, 30, 23, 59, tzinfo=UTC),
            "k": params.SCALE_K,
        }
    ]
    assert json.loads((tmp_path / "out" / PROGRESS_NAME).read_text(encoding="utf-8")) == report
    assert _history(tmp_path) == [
        {
            "run_at": DEC_1.isoformat(),
            "through": report["through"],
            "status": "running",
            "reason": None,
            "gap": None,
            "commit": commit,
        }
    ]


def test_progress_before_first_closed_month_writes_nothing(repo: tuple[Path, str], tmp_path: Path) -> None:
    root, _ = repo
    simulate = FakeSimulate(_segment())
    assert _run(root, tmp_path, datetime(2026, 11, 20, tzinfo=UTC), simulate) is None
    assert simulate.calls == []
    assert not (tmp_path / "out").exists()


def test_progress_kill_switch_trip_ends_the_test(repo: tuple[Path, str], tmp_path: Path) -> None:
    root, _ = repo
    report = _run(root, tmp_path, DEC_1, FakeSimulate(_segment(trips=1)))
    assert report is not None
    assert report["status"] == "ended: kill switch"
    assert report["reason"] == "tripped at 2026-11-20T05:00:00+00:00"
    assert report["kill_switch_trips"] == 1
    later = FakeSimulate(_segment())
    again = _run(root, tmp_path, JAN_1, later)
    assert later.calls == []
    assert again is not None
    assert again["status"] == "ended: kill switch"
    assert again["reason"] == "tripped at 2026-11-20T05:00:00+00:00"
    assert again["run_at"] == JAN_1.isoformat()
    assert len(_history(tmp_path)) == 2


def test_progress_after_the_end_keeps_the_last_figures(repo: tuple[Path, str], tmp_path: Path) -> None:
    root, _ = repo
    ended = _run(root, tmp_path, DEC_1, FakeSimulate(_segment(trips=1)))
    again = _run(root, tmp_path, JAN_1, FakeSimulate(_segment()))
    assert ended is not None and again is not None
    assert again == {**ended, "run_at": JAN_1.isoformat()}
    assert (again["net"], again["through"], again["days_done"]) == (12.5, "2026-11-30T23:59:00+00:00", 20)
    assert _history(tmp_path)[-1]["through"] == "2026-11-30T23:59:00+00:00"


def test_progress_gap_voids_after_two_more_months(repo: tuple[Path, str], tmp_path: Path) -> None:
    root, _ = repo
    reports = [_run(root, tmp_path, now, FakeSimulate()) for now in (DEC_1, JAN_1, FEB_1)]
    assert [report["status"] for report in reports if report] == [
        "incomplete data",
        "incomplete data",
        f"void: data gap not filled after 2 retries ({GAP})",
    ]
    assert reports[-1] is not None
    assert reports[-1]["data_gaps"] == [GAP]
    assert reports[-1]["net"] is None


def test_progress_same_month_rerun_does_not_count_as_retry(repo: tuple[Path, str], tmp_path: Path) -> None:
    root, _ = repo
    reports = [_run(root, tmp_path, DEC_1, FakeSimulate()) for _ in range(3)]
    assert [report["status"] for report in reports if report] == ["incomplete data"] * 3


def test_progress_a_different_gap_does_not_void(repo: tuple[Path, str], tmp_path: Path) -> None:
    root, _ = repo
    _run(root, tmp_path, DEC_1, FakeSimulate(gap="ETHUSDT: another gap"))
    _run(root, tmp_path, JAN_1, FakeSimulate())
    report = _run(root, tmp_path, FEB_1, FakeSimulate())
    assert report is not None
    assert report["status"] == "incomplete data"


def test_progress_frozen_mismatch_is_error(repo: tuple[Path, str], tmp_path: Path) -> None:
    root, _ = repo
    simulate = FakeSimulate(_segment())
    problems = ["changed: src/silvr/risk/engine.py"]
    report = _run(root, tmp_path, DEC_1, simulate, check=lambda _root: problems)
    assert report is not None
    assert report["status"] == "error"
    assert report["reason"] == "frozen files changed: changed: src/silvr/risk/engine.py"
    assert report["frozen_check"] == problems
    assert report["net"] is None
    assert simulate.calls == []


MAR_1 = datetime(2027, 3, 1, 1, 0, tzinfo=UTC)
NOV_THROUGH = "2026-11-30T23:59:00+00:00"


def _figures_of(report: dict[str, Any] | None) -> tuple[Any, ...]:
    assert report is not None
    return tuple(report[key] for key in ("through", "days_done", "net", "max_drawdown", "trades", "weekly_average"))


def test_gap_months_keep_the_last_good_figures_through_the_void(repo: tuple[Path, str], tmp_path: Path) -> None:
    root, _ = repo
    running = _run(root, tmp_path, DEC_1, FakeSimulate(_segment()))
    good = _figures_of(running)
    assert good == (NOV_THROUGH, 20, 12.5, 40.0, 4, 4.0)
    gap_runs = [_run(root, tmp_path, now, FakeSimulate()) for now in (JAN_1, FEB_1, MAR_1)]
    assert [report["status"] for report in gap_runs if report] == [
        "incomplete data",
        "incomplete data",
        f"void: data gap not filled after 2 retries ({GAP})",
    ]
    assert all(_figures_of(report) == good for report in gap_runs)
    assert all(report["data_gaps"] == [GAP] for report in gap_runs if report)
    assert [entry["through"] for entry in _history(tmp_path)] == [
        NOV_THROUGH,
        "2026-12-31T23:59:00+00:00",
        "2027-01-31T23:59:00+00:00",
        "2027-02-28T23:59:00+00:00",
    ]
    after = _run(root, tmp_path, datetime(2027, 4, 1, 1, 0, tzinfo=UTC), FakeSimulate(_segment()))
    assert _figures_of(after) == good


def test_error_month_keeps_the_last_good_figures(repo: tuple[Path, str], tmp_path: Path) -> None:
    root, _ = repo
    good = _figures_of(_run(root, tmp_path, DEC_1, FakeSimulate(_segment())))
    problems = ["changed: src/silvr/risk/engine.py"]
    report = _run(root, tmp_path, JAN_1, FakeSimulate(_segment()), check=lambda _root: problems)
    assert report is not None
    assert report["status"] == "error"
    assert report["frozen_check"] == problems
    assert report["run_at"] == JAN_1.isoformat()
    assert _figures_of(report) == good


def test_record_void_is_terminal(repo: tuple[Path, str], tmp_path: Path) -> None:
    root, _ = repo
    _run(root, tmp_path, DEC_1, FakeSimulate(_segment()))
    entry = record_void(tmp_path / "out", "bug in trend_engine", datetime(2026, 12, 5, tzinfo=UTC))
    assert entry["status"] == "void: bug in trend_engine"
    simulate = FakeSimulate(_segment())
    report = _run(root, tmp_path, JAN_1, simulate)
    assert report is not None
    assert report["status"] == "void: bug in trend_engine"
    assert report["reason"] == "bug in trend_engine"
    assert simulate.calls == []


def test_record_void_keeps_the_last_period_and_figures(repo: tuple[Path, str], tmp_path: Path) -> None:
    root, _ = repo
    running = _run(root, tmp_path, DEC_1, FakeSimulate(_segment()))
    assert running is not None
    void_at = datetime(2026, 12, 5, tzinfo=UTC)
    entry = record_void(tmp_path / "out", "bug in trend_engine", void_at)
    assert entry["through"] == running["through"]
    report = json.loads((tmp_path / "out" / PROGRESS_NAME).read_text(encoding="utf-8"))
    assert report == {
        **running,
        "status": "void: bug in trend_engine",
        "reason": "bug in trend_engine",
        "run_at": void_at.isoformat(),
    }
    later = _run(root, tmp_path, JAN_1, FakeSimulate(_segment()))
    assert later is not None
    assert (later["through"], later["days_done"], later["net"]) == (running["through"], 20, 12.5)


def test_progress_without_a_commit_is_error(tmp_path: Path) -> None:
    not_git = tmp_path / "not-git"
    not_git.mkdir()
    simulate = FakeSimulate(_segment())
    report = _run(not_git, tmp_path, DEC_1, simulate)
    assert report is not None
    assert report["status"] == "error"
    assert report["reason"].startswith("git cannot name the commit: ")
    assert report["frozen_check"] == "ok"
    assert report["commits"] == []
    assert simulate.calls == []
    assert _history(tmp_path)[-1]["commit"] is None


def test_record_void_refuses_after_the_test_has_ended(repo: tuple[Path, str], tmp_path: Path) -> None:
    """A void must not overwrite a FAIL (or a verdict): that would be a second shot at the year."""
    root, _ = repo
    _run(root, tmp_path, DEC_1, FakeSimulate(_segment(trips=1)))
    with pytest.raises(ValueError, match="already ended"):
        record_void(tmp_path / "out", "bug in trend_engine", JAN_1)
    assert len(_history(tmp_path)) == 1


def test_progress_commits_lists_each_commit_run_from(repo: tuple[Path, str], tmp_path: Path) -> None:
    root, first = repo
    _run(root, tmp_path, DEC_1, FakeSimulate(_segment()))
    (root / "a.py").write_text("a = 2\n")
    _git(root, "commit", "-q", "-am", "next")
    second = _git(root, "rev-parse", "HEAD")
    report = _run(root, tmp_path, JAN_1, FakeSimulate(_segment()))
    assert report is not None
    assert report["commits"] == [first, second]


# --- the one verdict ---------------------------------------------------------------------------------

VERDICT_NOW = datetime(2027, 12, 1, 1, 0, tzinfo=UTC)
FORWARD_END_ISO = "2027-11-10T23:59:00+00:00"


class FakeGate:
    """Stands in for gate.main: records argv, writes promotion_gate.json and one log line, returns `code`."""

    def __init__(self, passed: bool = True, code: int | None = None) -> None:
        self.passed = passed
        self.code = (0 if passed else 1) if code is None else code
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str]) -> int:
        self.calls.append(argv)
        if self.code == 2:  # the real gate writes nothing on an input error
            return 2
        folder = Path(argv[1]).parent
        (folder / OUTPUT_NAME).write_text(json.dumps({"passed": self.passed}), encoding="utf-8")
        with (folder / LOG_NAME).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"passed": self.passed}) + "\n")
        return self.code


def _verdict(tmp_path: Path, simulate: Any, gate_main: Any, now: datetime = VERDICT_NOW) -> str:
    return run_verdict(
        data_root=tmp_path / "data", output_dir=tmp_path / "out", now=now, simulate=simulate, gate_main=gate_main
    )


def test_verdict_runs_gate_once_and_reads_result(tmp_path: Path) -> None:
    gate_main = FakeGate(passed=True)
    assert _verdict(tmp_path, FakeSimulate(_segment()), gate_main) == "verdict PASS"
    assert gate_main.calls == [["--report", str(tmp_path / "out" / REPORT_NAME)]]


def test_verdict_fail_is_read_from_the_gate_output(tmp_path: Path) -> None:
    assert _verdict(tmp_path, FakeSimulate(_segment()), FakeGate(passed=False)) == "verdict FAIL"


@pytest.mark.parametrize(
    ("passed", "code"),
    [(True, 2), (True, 1), (False, 0), (True, 3)],
    ids=["input-error", "pass-file-fail-code", "fail-file-pass-code", "odd-code"],
)
def test_verdict_gate_error_or_disagreement_is_refused(tmp_path: Path, passed: bool, code: int) -> None:
    """An input error, or an exit code that disagrees with promotion_gate.json, is never a PASS or FAIL."""
    with pytest.raises(VerdictRefused):
        _verdict(tmp_path, FakeSimulate(_segment()), FakeGate(passed=passed, code=code))


def test_verdict_refused_when_log_has_a_line(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / LOG_NAME).write_text(json.dumps({"passed": False}) + "\n", encoding="utf-8")
    simulate, gate_main = FakeSimulate(_segment()), FakeGate()
    with pytest.raises(VerdictRefused, match="already given"):
        _verdict(tmp_path, simulate, gate_main)
    assert gate_main.calls == []
    assert simulate.calls == []


def test_verdict_refused_before_the_window_closes(tmp_path: Path) -> None:
    gate_main = FakeGate()
    with pytest.raises(VerdictRefused, match="not closed"):
        _verdict(tmp_path, FakeSimulate(_segment()), gate_main, now=datetime(2027, 11, 1, 1, 0, tzinfo=UTC))
    assert gate_main.calls == []


def test_verdict_refused_when_data_is_missing(tmp_path: Path) -> None:
    gate_main = FakeGate()
    with pytest.raises(VerdictRefused, match="data"):
        _verdict(tmp_path, FakeSimulate(), gate_main)
    assert gate_main.calls == []
    assert not (tmp_path / "out" / REPORT_NAME).exists()


def test_verdict_report_segments_use_original_and_forward_bounds(tmp_path: Path) -> None:
    simulate = FakeSimulate(_segment())
    _verdict(tmp_path, simulate, FakeGate())
    original = segment_bounds(ORIGINAL_FIRST, ORIGINAL_LAST)
    windows = [(call["start"], call["end"]) for call in simulate.calls]
    assert windows == [original["training"], original["validation"], (FORWARD_START, FORWARD_END)]
    assert all(call["k"] == params.SCALE_K for call in simulate.calls)
    assert all(call["candles_root"] == tmp_path / "data" / "candles" for call in simulate.calls)
    assert original["training"][0].isoformat() == "2022-01-01T00:00:00+00:00"
    assert FORWARD_END.isoformat() == FORWARD_END_ISO
    report = json.loads((tmp_path / "out" / REPORT_NAME).read_text(encoding="utf-8"))
    assert report["kind"] == "forward_verdict"
    assert report["strategy"] == params.STRATEGY_NAME
    assert report["symbols"] == list(params.SYMBOLS)
    assert report["k"] == params.SCALE_K
    assert report["parameters_tuned"] is False
    assert sorted(report["segments"]) == sorted(SEGMENT_NAMES)


def _gate_segment(**window: Any) -> dict[str, Any]:
    """A segment the real gate can judge, carrying the window it was asked for."""
    segment = _segment()
    segment["metrics"] |= {
        "total_trades": 120,
        "average_r": 0.30,
        "r_t_stat": 2.5,
        "profit_factor": 1.8,
        "realized_rr": 1.7,
        "max_drawdown_percent": 0.06,
        "return_to_drawdown": 5.0,
    }
    return {**segment, "candles": 10, "start": window["start"].isoformat(), "end": window["end"].isoformat()}


def test_verdict_with_the_real_gate_is_look_one_and_cannot_repeat(tmp_path: Path) -> None:
    def simulate(**kwargs: Any) -> dict[str, Any]:
        return _gate_segment(**kwargs)

    assert _verdict(tmp_path, simulate, gate.main) == "verdict PASS"
    out = tmp_path / "out"
    result = json.loads((out / OUTPUT_NAME).read_text(encoding="utf-8"))
    assert result["passed"] is True
    assert result["t_stat_bar"] == 2.0
    lines = (out / LOG_NAME).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    logged = json.loads(lines[0])
    assert (logged["data_start"], logged["data_end"]) == ("2022-01-01T00:00:00+00:00", FORWARD_END_ISO)
    with pytest.raises(VerdictRefused, match="already given"):
        _verdict(tmp_path, simulate, gate.main)
    assert len((out / LOG_NAME).read_text(encoding="utf-8").splitlines()) == 1


def test_progress_at_the_window_end_gives_the_verdict(repo: tuple[Path, str], tmp_path: Path) -> None:
    root, _ = repo
    _run(root, tmp_path, DEC_1, FakeSimulate(_segment()))
    gate_main = FakeGate(passed=False)
    verdict = partial(run_verdict, gate_main=gate_main)
    report = _run(root, tmp_path, VERDICT_NOW, FakeSimulate(_segment()), verdict=verdict)
    assert report is not None
    assert report["status"] == "verdict FAIL"
    assert report["through"] == FORWARD_END_ISO
    assert len(gate_main.calls) == 1
    assert _history(tmp_path)[-1]["status"] == "verdict FAIL"


def test_progress_after_verdict_reports_stored_verdict(repo: tuple[Path, str], tmp_path: Path) -> None:
    root, _ = repo
    verdict = partial(run_verdict, gate_main=FakeGate())
    first = _run(root, tmp_path, VERDICT_NOW, FakeSimulate(_segment()), verdict=verdict)
    assert first is not None and first["status"] == "verdict PASS"
    simulate, gate_main = FakeSimulate(_segment()), FakeGate(passed=False)
    later_now = datetime(2028, 1, 1, 1, 0, tzinfo=UTC)
    later = _run(root, tmp_path, later_now, simulate, verdict=partial(run_verdict, gate_main=gate_main))
    assert later is not None
    assert later["status"] == "verdict PASS"
    assert simulate.calls == []
    assert gate_main.calls == []


def test_progress_verdict_refusal_is_error_with_last_figures(repo: tuple[Path, str], tmp_path: Path) -> None:
    root, _ = repo
    good = _figures_of(_run(root, tmp_path, DEC_1, FakeSimulate(_segment())))
    verdict = partial(run_verdict, gate_main=FakeGate(code=2))
    report = _run(root, tmp_path, VERDICT_NOW, FakeSimulate(_segment()), verdict=verdict)
    assert report is not None
    assert report["status"] == "error"
    assert report["reason"].startswith("verdict refused: ")
    assert _figures_of(report) == good
    assert _history(tmp_path)[-1]["status"] == "error"


def test_progress_report_is_refused_by_the_gate(repo: tuple[Path, str], tmp_path: Path) -> None:
    root, _ = repo
    report = _run(root, tmp_path, DEC_1, FakeSimulate(_segment()))
    assert report is not None
    with pytest.raises(GateInputError, match="forward progress report is not a gate input"):
        evaluate_gate(report)
