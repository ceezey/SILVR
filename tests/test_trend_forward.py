"""Tests for the trend_ensemble forward test: frozen-files check, fixed-window simulation, progress report."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from silvr.backtest.reporting import json_safe
from silvr.backtest.trend_engine import TrendDataError
from silvr.backtest.trend_forward import (
    FORWARD_END,
    FORWARD_START,
    HISTORY_NAME,
    NOTE,
    PROGRESS_NAME,
    backtest_config,
    check_frozen,
    head_commit,
    last_closed_minute,
    record_void,
    run_progress,
    simulate_window,
)
from silvr.backtest.trend_runner import SEGMENT_NAMES, run_trend_backtest, segment_bounds
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
    root: Path, tmp_path: Path, now: datetime, simulate: FakeSimulate, check: Any = _no_problems
) -> dict[str, Any] | None:
    return run_progress(
        repo_root=root,
        data_root=tmp_path / "data",
        output_dir=tmp_path / "out",
        now=now,
        simulate=simulate,
        check=check,
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
