"""Tests for the trend_ensemble forward test: frozen-files check and the fixed-window simulation."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from silvr.backtest.reporting import json_safe
from silvr.backtest.trend_engine import TrendDataError
from silvr.backtest.trend_forward import (
    FORWARD_END,
    backtest_config,
    check_frozen,
    last_closed_minute,
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
