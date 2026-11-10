"""Forward test of the frozen trend_ensemble backtest.

The trend_ensemble run is frozen at FREEZE_COMMIT and replayed on data from 2026-11-11 onward, with one
verdict after 2027-11-10. check_frozen proves the trade-deciding code is unchanged since that commit.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

FREEZE_COMMIT = "d6045a859d2afea8d28f44b7a4ed2a8aacfdeee4"

FROZEN_PATHS = (
    "src/silvr/strategy/trend",
    "src/silvr/backtest/trend_engine.py",
    "src/silvr/backtest/trend_runner.py",
    "src/silvr/backtest/sim_kill_switch.py",
    "src/silvr/backtest/metrics.py",
    "src/silvr/backtest/costs.py",
    "src/silvr/backtest/models.py",
    "src/silvr/risk",
    "src/silvr/data/csv_loader.py",
    "src/silvr/data/funding.py",
    "src/silvr/data/resample.py",
    "src/silvr/models.py",
)

FORWARD_START = datetime(2026, 11, 11, tzinfo=UTC)
FORWARD_END = datetime(2027, 11, 10, 23, 59, tzinfo=UTC)
ORIGINAL_FIRST = datetime(2022, 1, 1, tzinfo=UTC)
ORIGINAL_LAST = datetime(2026, 10, 20, 23, 59, tzinfo=UTC)


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True)


def check_frozen(
    repo_root: Path, *, commit: str = FREEZE_COMMIT, paths: tuple[str, ...] = FROZEN_PATHS
) -> list[str]:
    """Return one plain problem per frozen path that differs from `commit`; an empty list means frozen.

    Fails closed: a git error, an unknown commit or a missing git binary is itself a problem.
    """
    problems: list[str] = []
    for label, args in (
        ("changed", ("diff", "--name-only", commit, "--", *paths)),
        ("untracked", ("ls-files", "--others", "--exclude-standard", "--", *paths)),
    ):
        try:
            result = _git(repo_root, *args)
        except OSError as exc:
            return [f"cannot run git: {exc}"]
        if result.returncode != 0:
            return [f"git {args[0]} failed: {result.stderr.strip() or 'no error text'}"]
        problems += [f"{label}: {name}" for name in result.stdout.splitlines() if name.strip()]
    return problems


def head_commit(repo_root: Path) -> str:
    """Return the full SHA of HEAD in `repo_root`; raise RuntimeError if git cannot say."""
    try:
        result = _git(repo_root, "rev-parse", "HEAD")
    except OSError as exc:
        raise RuntimeError(f"cannot run git: {exc}") from exc
    if result.returncode != 0:
        raise RuntimeError(f"git rev-parse HEAD failed: {result.stderr.strip()}")
    return result.stdout.strip()
