"""Forward test of the frozen trend_ensemble backtest.

The trend_ensemble run is frozen at FREEZE_COMMIT and replayed on data from 2026-11-11 onward, with one
verdict after 2027-11-10. check_frozen proves the trade-deciding code is unchanged since that commit;
run_progress writes the monthly progress report (never a verdict) and keeps the status history.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from silvr.backtest.models import BacktestConfig
from silvr.backtest.reporting import json_safe
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

KIND = "forward_progress"
PROGRESS_NAME = "forward_progress.json"
HISTORY_NAME = "forward_history.jsonl"
NOTE = "Progress only. No verdict until 2027-11-10. Do not change the strategy because of this number."
GAP_RETRIES = 2
DAYS_TOTAL = 365

_INCOMPLETE = "incomplete data"
_ENDED = ("ended: kill switch", "verdict PASS", "verdict FAIL")


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


def _is_terminal(status: str) -> bool:
    return status in _ENDED or status.startswith("void: ")


def _read_history(output_dir: Path) -> list[dict[str, Any]]:
    path = output_dir / HISTORY_NAME
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _read_progress(output_dir: Path) -> dict[str, Any] | None:
    path = output_dir / PROGRESS_NAME
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _write_progress(output_dir: Path, report: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / PROGRESS_NAME).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def _distinct(commits: list[str | None]) -> list[str]:
    return list(dict.fromkeys(sha for sha in commits if sha))


def _append_history(output_dir: Path, entry: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / HISTORY_NAME).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(json_safe(entry), sort_keys=True) + "\n")


def _gap_not_filled(history: list[dict[str, Any]], through: str, gap: str) -> bool:
    """True when the latest entries of the GAP_RETRIES previous distinct `through` months all hold `gap`.

    Reruns for the same month do not count as retries: only a later month's download is a new attempt.
    """
    latest: dict[str, dict[str, Any]] = {}
    for entry in reversed(history):
        month = entry["through"]
        if month != through and month not in latest:
            latest[month] = entry
            if len(latest) == GAP_RETRIES:
                break
    return len(latest) == GAP_RETRIES and all(
        entry["status"] == _INCOMPLETE and entry["gap"] == gap for entry in latest.values()
    )


def _figures(segment: dict[str, Any] | None) -> dict[str, Any]:
    """The dollar and trade figures of one simulated segment; all None when nothing was simulated."""
    metrics = (segment or {}).get("metrics") or {}
    weekly = (segment or {}).get("success_standard") or {}
    return {
        "net": metrics.get("net_profit"),
        "max_drawdown": metrics.get("max_drawdown"),
        "fees": metrics.get("total_fees"),
        "funding": metrics.get("total_funding"),
        "trades": metrics.get("total_trades"),
        "average_r": metrics.get("average_r"),
        "profit_factor": metrics.get("profit_factor"),
        "realized_rr": metrics.get("realized_rr"),
        "weekly_average": weekly.get("average_weekly_net"),
        "weekly_target": weekly.get("target_weekly_net"),
        "losing_week_share": weekly.get("losing_week_share"),
        "worst_week": weekly.get("worst_week"),
        "kill_switch_trips": segment["kill_switch"]["trips"] if segment else None,
    }


def run_progress(
    *,
    repo_root: Path,
    data_root: Path,
    output_dir: Path,
    now: datetime,
    simulate: Callable[..., dict[str, Any]] = simulate_window,
    check: Callable[[Path], list[str]] = check_frozen,
) -> dict[str, Any] | None:
    """Write the progress report for FORWARD_START to the last closed month and append its history line.

    Returns the report, or None (writing nothing) before the first month has closed. The status follows
    the rules in order: an ended test stays ended (no simulation); a frozen-files mismatch, or a commit
    git cannot name, is `error`; missing data is `incomplete data`, or void once the same gap survives
    GAP_RETRIES later months; a kill-switch trip ends the test; otherwise `running`. A run that simulates
    nothing keeps the last good month's period and figures. This is progress only, never a verdict.
    """
    through: datetime | None = last_closed_minute(now)
    if through < FORWARD_START:
        return None
    history = _read_history(output_dir)
    problems = list(check(repo_root))
    commit: str | None = None
    commit_error: str | None = None
    try:
        commit = head_commit(repo_root)
    except RuntimeError as exc:  # a run must name its commit; without one it is an error, not a guess
        commit_error = str(exc)

    reason: str | None = None
    gap: str | None = None
    segment: dict[str, Any] | None = None
    last = history[-1] if history else None
    ended = last is not None and _is_terminal(last["status"])
    if last is not None and ended:
        status, reason, gap = last["status"], last["reason"], last["gap"]
        through = datetime.fromisoformat(last["through"]) if last["through"] else None
    elif problems:
        status, reason = "error", "frozen files changed: " + "; ".join(problems)
    elif commit_error is not None:
        status, reason = "error", f"git cannot name the commit: {commit_error}"
    else:
        try:
            segment = simulate(
                candles_root=data_root / "candles",
                funding_root=data_root / "funding",
                start=FORWARD_START,
                end=through,
                k=params.SCALE_K,
            )
        except TrendDataError as exc:
            gap = reason = str(exc)
            status = _INCOMPLETE
            if _gap_not_filled(history, through.isoformat(), gap):
                reason = f"data gap not filled after {GAP_RETRIES} retries ({gap})"
                status = f"void: {reason}"
        else:
            if segment["kill_switch"]["trips"] >= 1:
                status = "ended: kill switch"
                reason = f"tripped at {json_safe(segment['kill_switch']['tripped_at'])}"
            else:
                status = "running"

    run_at = now.astimezone(UTC)
    commits = _distinct([entry["commit"] for entry in history] + [commit])
    previous = _read_progress(output_dir)
    if segment is None and previous is not None:
        # Nothing new was simulated: keep the last good month's period and figures; the status, reason
        # and (unless the test had already ended) the data gaps and frozen check carry this run's news.
        changes: dict[str, Any] = {"status": status, "reason": reason, "run_at": run_at, "commits": commits}
        if not ended:
            changes |= {"data_gaps": [gap] if gap else [], "frozen_check": problems or "ok"}
        report = {**previous, **json_safe(changes)}
    else:
        report = json_safe(
            {
                "kind": KIND,
                "strategy": params.STRATEGY_NAME,
                "status": status,
                "reason": reason,
                "forward_start": FORWARD_START,
                "forward_end": FORWARD_END,
                "through": through,
                "days_done": (through - FORWARD_START + _MINUTE).days if through else None,
                "days_total": DAYS_TOTAL,
                **_figures(segment),
                "data_gaps": [gap] if gap else [],
                "commits": commits,
                "frozen_check": problems or "ok",
                "note": NOTE,
                "run_at": run_at,
            }
        )
    _write_progress(output_dir, report)
    _append_history(
        output_dir,
        {  # `through` is the month this run attempted, so same-month reruns stay apart from retries
            "run_at": run_at,
            "through": through,
            "status": status,
            "reason": reason,
            "gap": gap,
            "commit": commit,
        },
    )
    return report


def record_void(output_dir: Path, reason: str, now: datetime) -> dict[str, Any]:
    """End the test as `void: <reason>` by hand (a confirmed frozen-file bug, a delisted coin).

    Returns the history entry it appended.

    The progress file, if any, keeps its last known figures and period with the void status. Later runs
    copy the void and simulate nothing. Refuses once the test has ended, so a void can never replace a
    kill-switch FAIL or a verdict.
    """
    history = _read_history(output_dir)
    if history and _is_terminal(history[-1]["status"]):
        raise ValueError(f"the forward test has already ended: {history[-1]['status']}")
    previous = _read_progress(output_dir)
    entry = json_safe(
        {
            "run_at": now.astimezone(UTC),
            "through": previous["through"] if previous else None,
            "status": f"void: {reason}",
            "reason": reason,
            "gap": None,
            "commit": None,
        }
    )
    if previous is not None:
        changes = {"status": entry["status"], "reason": reason, "run_at": entry["run_at"]}
        _write_progress(output_dir, {**previous, **changes})
    _append_history(output_dir, entry)
    return entry
