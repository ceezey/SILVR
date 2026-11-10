"""Forward test of the frozen trend_ensemble backtest.

The trend_ensemble run is frozen at FREEZE_COMMIT and replayed on data from 2026-11-11 onward, with one
verdict after 2027-11-10. check_frozen proves the trade-deciding code is unchanged since that commit.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from silvr.backtest.models import BacktestConfig
from silvr.backtest.trend_engine import TrendDataError, TrendPortfolioEngine
from silvr.backtest.trend_runner import (
    _MINUTE,
    _check_months,
    _history,
    _minutes,
    _month_candles,
    _month_files,
    realized_volatility,
    success_standard,
)
from silvr.data.funding import FundingDataError, FundingSchedule, load_funding_csv
from silvr.risk import RiskConfig
from silvr.strategy.trend import params

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


def last_closed_minute(now: datetime) -> datetime:
    """Last 1m open time of the UTC month before `now`'s UTC month, capped at FORWARD_END."""
    first_of_month = now.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return min(first_of_month - _MINUTE, FORWARD_END)


def backtest_config() -> BacktestConfig:
    """The config `trend_runner.run_trend_backtest` builds (frozen values)."""
    return BacktestConfig(
        initial_balance=params.INITIAL_BALANCE, risk=RiskConfig.trend(), slippage_bps=5.0, spread_bps=3.0
    )


def _require_candle(files: dict[str, dict[str, Path]], symbol: str, when: datetime) -> None:
    """Raise TrendDataError unless `symbol` has a 1m candle opening exactly at `when`."""
    path = files[symbol].get(f"{when:%Y-%m}")
    if path is None or when not in {candle.open_time for candle in _month_candles(path, symbol)}:
        raise TrendDataError(symbol, when, "data does not cover the window")


def simulate_window(
    *, candles_root: Path, funding_root: Path, start: datetime, end: datetime, k: float
) -> dict[str, Any]:
    """Run the frozen engine over [start, end] and return one segment dict like `run_trend_backtest` writes.

    The engine checks minute continuity only from the first minute it sees and `_minutes` stops quietly
    when data runs out, so the lead symbol must have a candle at `start` and at `end` here, or this raises.
    """
    files = {symbol: _month_files(candles_root, symbol) for symbol in params.SYMBOLS}
    _check_months(files)
    lead = params.SYMBOLS[0]
    _require_candle(files, lead, start)
    _require_candle(files, lead, end)
    funding = {
        symbol: FundingSchedule(load_funding_csv(Path(funding_root) / f"{symbol}-funding.csv"))
        for symbol in params.SYMBOLS
    }
    for symbol in params.SYMBOLS:
        try:
            funding[symbol].check_coverage(start, end)
        except FundingDataError as exc:
            raise TrendDataError(symbol, None, f"funding for the window: {exc}") from exc

    config = backtest_config()
    engine = TrendPortfolioEngine(config, funding=funding, history=_history(files, start), k=k)
    result = engine.run(_minutes(files, start, end))
    tripped = result.kill_switch_tripped_at
    return {
        "candles": (int((end - start) / _MINUTE) + 1) * len(params.SYMBOLS),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "metrics": result.metrics,
        "kill_switch": {"trips": int(tripped is not None), "tripped_at": tripped},
        "simulated_kill_switch": result.simulated_kill_switch,
        "success_standard": success_standard(result.daily_equity, config.initial_balance),
        "realized_volatility": realized_volatility(result.daily_equity, config.initial_balance),
        "rejections": dict(result.rejections),
    }
