"""Tests for the trend_ensemble forward test: frozen-files check."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from silvr.backtest.trend_forward import check_frozen

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
