"""Forward test of the frozen trend_ensemble backtest.

The trend_ensemble run is frozen at FREEZE_COMMIT and replayed on data from 2026-11-11 onward, with one
verdict after 2027-11-10. check_frozen proves the trade-deciding code is unchanged since that commit;
run_progress writes the monthly progress report (never a verdict) and keeps the status history;
run_verdict, called once by run_progress when the window has closed, runs the gate on the one verdict report.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import traceback
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import silvr
from silvr.backtest import gate
from silvr.backtest.models import BacktestConfig
from silvr.backtest.reporting import json_safe
from silvr.backtest.trend_engine import TrendDataError, TrendPortfolioEngine

# trend_runner is frozen at FREEZE_COMMIT, so these private names cannot change without ending the test.
from silvr.backtest.trend_runner import (
    _MINUTE,
    REPORT_NAME,
    _check_months,
    _history,
    _minutes,
    _month_candles,
    _month_files,
    realized_volatility,
    segment_bounds,
    success_standard,
)
from silvr.data.download import download, download_funding
from silvr.data.funding import FundingDataError, FundingSchedule, load_funding_csv
from silvr.exchange.binance_futures import BinanceFuturesAdapter
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

# The code each history line records by git blob hash, so a later reader can tell which version ran.
CODE_PATHS = ("src/silvr/backtest/trend_forward.py", "src/silvr/backtest/gate.py", "src/silvr/data/download.py")

# gate.py's thresholds when the forward test was frozen (2026-11-11); the verdict refuses if any has moved.
GATE_THRESHOLDS = {
    "MIN_TRADES": 100,
    "MIN_T_STAT": 2.0,
    "MIN_T_STAT_REPEAT": 3.0,
    "MIN_PROFIT_FACTOR": 1.5,
    "MIN_REALIZED_RR": 1.5,
    "MAX_DRAWDOWN_PERCENT_BY_STRATEGY[trend_ensemble]": 0.30,
    "MIN_RETURN_TO_DRAWDOWN": 2.0,
    "MIN_OOS_EFFICIENCY": 0.5,
}


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


def code_hashes(repo_root: Path) -> dict[str, str]:
    """The git blob hash of each CODE_PATHS file in `repo_root`; a git failure records its error text instead."""
    hashes: dict[str, str] = {}
    for path in CODE_PATHS:
        try:
            result = _git(repo_root, "hash-object", path)
        except OSError as exc:
            hashes[path] = f"cannot run git: {exc}"
            continue
        error = result.stderr.strip() or "no error text"
        hashes[path] = result.stdout.strip() if result.returncode == 0 else f"git hash-object failed: {error}"
    return hashes


def head_commit(repo_root: Path) -> str:
    """Return the full SHA of HEAD in `repo_root`; raise RuntimeError if git cannot say."""
    try:
        result = _git(repo_root, "rev-parse", "HEAD")
    except OSError as exc:
        raise RuntimeError(f"cannot run git: {exc}") from exc
    if result.returncode != 0:
        raise RuntimeError(f"git rev-parse HEAD failed: {result.stderr.strip()}")
    return result.stdout.strip()


def check_import(repo_root: Path, *, silvr_file: str | Path | None = None) -> str | None:
    """None when the running silvr package is the one under `repo_root/src`, else the problem in plain words.

    check_frozen checks the files in `repo_root`; this proves those files are the code that runs (a plain
    `pip install .` or another checkout's editable install would run a copy).
    """
    src = (repo_root / "src").resolve()
    actual = Path(silvr_file or silvr.__file__).resolve()
    if actual.is_relative_to(src):
        return None
    return f"silvr is not imported from {src} ({actual}); install with pip install -e ."


def last_closed_minute(now: datetime) -> datetime:
    """Last 1m open time of the UTC month before `now`'s UTC month, capped at FORWARD_END.

    Once the window's last minute has closed (from 2027-11-11 00:00 UTC) it is FORWARD_END itself, so the
    verdict can be run by hand then (spec section 5).
    """
    if now >= FORWARD_END + _MINUTE:
        return FORWARD_END
    first_of_month = now.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return min(first_of_month - _MINUTE, FORWARD_END)


def _download_end(now: datetime) -> datetime:
    """Exclusive end of a download: the first instant of `now`'s UTC month.

    Once the window has closed (`now >= FORWARD_END + 1 minute`) it is one minute past FORWARD_END instead.
    """
    now = now.astimezone(UTC)
    if now >= FORWARD_END + _MINUTE:
        return FORWARD_END + _MINUTE
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _candle_dir(candles_root: Path, symbol: str) -> Path:
    """The folder holding the symbol's newest month file, or `candles_root/<symbol>` when it has none yet.

    The owner's BTCUSDT files sit flat in candles/ while the others have a folder each; writing a month into
    a second folder would make the runner refuse the duplicate file every month.
    """
    existing = list(candles_root.rglob(f"{symbol}-1m-*.csv"))
    return max(existing, key=lambda path: path.name).parent if existing else candles_root / symbol


async def _download_all(
    data_root: Path, end: datetime, adapter: BinanceFuturesAdapter, scratch: Path, problems: list[str]
) -> None:
    for symbol in params.SYMBOLS:
        try:
            await download(
                symbol=symbol,
                timeframe="1m",
                start=date(2026, 10, 1),
                end=end,
                out_dir=_candle_dir(data_root / "candles", symbol),
                adapter=adapter,
            )
        except Exception as exc:  # a failed symbol is a problem to report, not a reason to skip the rest
            problems.append(f"{symbol}: candle download failed: {exc}")
        try:
            new = await download_funding(
                symbol=symbol, start=ORIGINAL_FIRST.date(), end=end, out_dir=scratch, adapter=adapter
            )
            if new is None:
                problems.append(f"{symbol}: funding download returned no rates; kept the old file")
                continue
            FundingSchedule(load_funding_csv(new)).check_coverage(ORIGINAL_FIRST, end - _MINUTE)
            target = data_root / "funding" / new.name
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(new, target)
        except Exception as exc:  # includes FundingDataError: the new file is partial, the old one stays
            problems.append(f"{symbol}: funding not replaced, kept the old file: {exc}")


def download_new_data(data_root: Path, now: datetime, *, adapter: BinanceFuturesAdapter | None = None) -> list[str]:
    """Download the 1m candles from 2026-10-01 and the funding rates from ORIGINAL_FIRST up to the download end.

    The end is the first instant of `now`'s UTC month, or, once the window has closed, one minute past
    FORWARD_END. Candles go straight into the folder each symbol's files already sit in, or
    `data_root/candles/<symbol>` for a symbol with none (download skips complete months and writes each file
    atomically). Funding goes to a temporary folder first and replaces the real file only
    when it covers ORIGINAL_FIRST to the last minute before the end, so a partial answer never overwrites a
    good file. Returns one plain problem per failure; a failed symbol never stops the others.
    """
    problems: list[str] = []
    end = _download_end(now)
    # The adapter closes its own client after every request, so there is nothing to close here.
    adapter = adapter or BinanceFuturesAdapter()
    # The scratch folder sits beside funding/ so os.replace never crosses volumes (it fails on Windows).
    data_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=data_root) as scratch:
        asyncio.run(_download_all(data_root, end, adapter, Path(scratch), problems))
    return problems


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


def _run_month(run_at: datetime | str) -> str:
    """The UTC month ("2027-12") a run happened in."""
    when = datetime.fromisoformat(run_at) if isinstance(run_at, str) else run_at
    return f"{when.astimezone(UTC):%Y-%m}"


def _gap_not_filled(history: list[dict[str, Any]], now: datetime, gap: str) -> bool:
    """True when the latest entries of the GAP_RETRIES previous distinct UTC run months all hold `gap`.

    Reruns in the same month do not count as retries: only a later month's download is a new attempt. The
    run month, not `through`, is counted, because `through` stays FORWARD_END once the window has closed.
    """
    current = _run_month(now)
    latest: dict[str, dict[str, Any]] = {}
    for entry in reversed(history):
        month = _run_month(entry["run_at"])
        if month != current and month not in latest:
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


class VerdictRefused(Exception):
    """The one verdict cannot be given; the message says why in plain words."""


def _log_lines(output_dir: Path) -> list[str]:
    path = output_dir / gate.LOG_NAME
    if not path.exists():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _gate_threshold_changes() -> list[str]:
    """One "NAME pinned -> now" per gate threshold that differs from GATE_THRESHOLDS."""
    now = {name: getattr(gate, name, None) for name in GATE_THRESHOLDS}
    now["MAX_DRAWDOWN_PERCENT_BY_STRATEGY[trend_ensemble]"] = gate.MAX_DRAWDOWN_PERCENT_BY_STRATEGY.get(
        "trend_ensemble"
    )
    return [f"{name} {pinned!r} -> {now[name]!r}" for name, pinned in GATE_THRESHOLDS.items() if now[name] != pinned]


def _verdict_logged_elsewhere(repo_root: Path) -> Path | None:
    """The first gate log under `repo_root/reports` holding a look at the forward verdict range.

    Fails closed like the gate: a line that cannot be read raises VerdictRefused, since skipping it could
    hide an earlier verdict.
    """
    verdict_range = (ORIGINAL_FIRST.isoformat(), FORWARD_END.isoformat())
    for path in sorted((repo_root / "reports").rglob(gate.LOG_NAME)):
        for number, line in enumerate(_log_lines(path.parent), start=1):
            try:
                past = json.loads(line)
                logged = (past.get("data_start"), past.get("data_end"))
            except (ValueError, AttributeError) as exc:
                raise VerdictRefused(f"cannot read {path} line {number}: {exc}") from exc
            if logged == verdict_range:
                return path
    return None


def run_verdict(
    *,
    repo_root: Path,
    data_root: Path,
    output_dir: Path,
    now: datetime,
    simulate: Callable[..., dict[str, Any]] = simulate_window,
    gate_main: Callable[[list[str]], int] = gate.main,
    check: Callable[[Path], list[str]] = check_frozen,
) -> str:
    """Write the one forward verdict report, run the promotion gate on it and return `verdict PASS`/`FAIL`.

    training and validation are the original range's segments (the efficiency reference, recomputed by the
    same code); final_test is the forward window. The report sits in `output_dir`, so the gate's log is that
    folder's own: a data range nobody has looked at, look 1, t-bar 2.0. Raises VerdictRefused, before the
    gate runs, if that log already holds a look, any gate log under `repo_root/reports` holds a look at the
    forward range, a gate threshold differs from GATE_THRESHOLDS, `check` finds a frozen file changed, the
    window has not closed or data is missing; and after it, if the gate rejects the input or its exit code
    and promotion_gate.json disagree.
    """
    if _log_lines(output_dir):
        raise VerdictRefused(f"a verdict was already given: {output_dir / gate.LOG_NAME} holds a gate run")
    if (elsewhere := _verdict_logged_elsewhere(repo_root)) is not None:
        raise VerdictRefused(f"a verdict on this range already exists: {elsewhere}")
    if changes := _gate_threshold_changes():
        raise VerdictRefused("gate thresholds changed: " + "; ".join(changes))
    if problems := check(repo_root):
        raise VerdictRefused("frozen files changed: " + "; ".join(problems))
    through = last_closed_minute(now)
    if through != FORWARD_END:
        raise VerdictRefused(f"the forward window has not closed: data is closed only through {through.isoformat()}")
    windows = {**segment_bounds(ORIGINAL_FIRST, ORIGINAL_LAST), "final_test": (FORWARD_START, FORWARD_END)}
    try:
        segments = {
            name: simulate(
                candles_root=data_root / "candles",
                funding_root=data_root / "funding",
                start=start,
                end=end,
                k=params.SCALE_K,
            )
            for name, (start, end) in windows.items()
        }
    except TrendDataError as exc:
        raise VerdictRefused(f"data is missing: {exc}") from exc

    report = {
        "strategy": params.STRATEGY_NAME,
        "symbols": list(params.SYMBOLS),
        "k": params.SCALE_K,
        "parameters_tuned": False,
        "kind": "forward_verdict",
        "segments": segments,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / REPORT_NAME
    path.write_text(json.dumps(json_safe(report), indent=2, sort_keys=True), encoding="utf-8")
    code = gate_main(["--report", str(path)])
    if code == 2:
        raise VerdictRefused("the gate rejected the verdict report as input (exit 2); see its error output")
    # The gate writes its result before its log line, so exactly one line proves the result is this run's.
    if len(_log_lines(output_dir)) != 1:
        raise VerdictRefused(f"the gate log should hold exactly this one run after exit {code}")
    try:
        passed = json.loads((output_dir / gate.OUTPUT_NAME).read_text(encoding="utf-8"))["passed"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise VerdictRefused(f"cannot read the gate result {gate.OUTPUT_NAME}: {exc}") from exc
    if code == 0 and passed is True:
        return "verdict PASS"
    if code == 1 and passed is False:
        return "verdict FAIL"
    raise VerdictRefused(f"the gate exit code {code} disagrees with {gate.OUTPUT_NAME} passed={passed!r}")


def _fresh_report(
    *,
    status: str,
    reason: str | None,
    through: datetime | None,
    segment: dict[str, Any] | None,
    gap: str | None,
    commits: list[str],
    frozen_check: list[str] | str,
    run_at: datetime,
) -> dict[str, Any]:
    """A whole progress report; a `segment` of None leaves every figure None."""
    return json_safe(
        {
            "kind": KIND,
            "strategy": params.STRATEGY_NAME,
            "status": status,
            "reason": reason,
            "forward_start": FORWARD_START,
            "forward_end": FORWARD_END,
            "through": through,
            "days_done": (through - FORWARD_START + _MINUTE).days if through and segment is not None else None,
            "days_total": DAYS_TOTAL,
            **_figures(segment),
            "data_gaps": [gap] if gap else [],
            "commits": commits,
            "frozen_check": frozen_check,
            "note": NOTE,
            "run_at": run_at,
        }
    )


def run_progress(
    *,
    repo_root: Path,
    data_root: Path,
    output_dir: Path,
    now: datetime,
    simulate: Callable[..., dict[str, Any]] = simulate_window,
    check: Callable[[Path], list[str]] = check_frozen,
    imported: Callable[[Path], str | None] = check_import,
    verdict: Callable[..., str] = run_verdict,
    download_problems: list[str] | None = None,
) -> dict[str, Any] | None:
    """Write the progress report for FORWARD_START to the last closed month and append its history line.

    Returns the report, or None (writing nothing) before the first month has closed. The status follows
    the rules in order: an ended test (a verdict included) stays ended (no simulation); silvr imported from
    anywhere but `repo_root/src`, a frozen-files mismatch, or a commit git cannot name, is `error`; missing
    data is `incomplete data`, or void once the same gap survives GAP_RETRIES later months; a kill-switch trip
    ends the test; otherwise `running`, or, once the whole window has closed, the one verdict from `verdict`
    (`error` if it refuses). A run that simulates nothing keeps the last good month's period and figures (a
    first run with nothing to keep has no `days_done`). Each history line records `code_hashes`. The report
    itself is never a gate input.

    `download_problems` are the failures of this run's download. Missing data that follows a failed download
    is `error` ("download failed: ..."), never `incomplete data`, so a network outage cannot count toward the
    void. With complete data the problems change nothing here.
    """
    through: datetime | None = last_closed_minute(now)
    if through < FORWARD_START:
        return None
    history = _read_history(output_dir)
    import_problem = imported(repo_root)
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
    elif import_problem is not None:
        status, reason = "error", import_problem
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
            if download_problems:
                status, reason = "error", "download failed: " + "; ".join(download_problems)
            elif _gap_not_filled(history, now, gap):
                reason = f"data gap not filled after {GAP_RETRIES} retries ({gap})"
                status = f"void: {reason}"
        else:
            if segment["kill_switch"]["trips"] >= 1:
                status = "ended: kill switch"
                reason = f"tripped at {json_safe(segment['kill_switch']['tripped_at'])}"
            else:
                status = "running"
                if through == FORWARD_END:
                    try:
                        status = verdict(
                            repo_root=repo_root,
                            data_root=data_root,
                            output_dir=output_dir,
                            now=now,
                            simulate=simulate,
                            check=check,
                        )
                    except VerdictRefused as exc:  # never a PASS/FAIL; keep the last good figures
                        status, reason, segment = "error", f"verdict refused: {exc}", None

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
        report = _fresh_report(
            status=status,
            reason=reason,
            through=through,
            segment=segment,
            gap=gap,
            commits=commits,
            frozen_check=problems or "ok",
            run_at=run_at,
        )
    _write_progress(output_dir, report)
    _append_history(
        output_dir,
        {  # `through` is the month this run attempted; `run_at` gives the run month that gap retries count
            "run_at": run_at,
            "through": through,
            "status": status,
            "reason": reason,
            "gap": gap,
            "commit": commit,
            "code": code_hashes(repo_root),
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


def record_error(output_dir: Path, reason: str, now: datetime) -> None:
    """Write `error` with `reason` over the progress file and history, keeping the last good figures.

    For a run that crashed before it could report. Does nothing once the test has ended, so a crash can
    never replace a kill-switch FAIL, a verdict or a void.
    """
    history = _read_history(output_dir)
    if history and _is_terminal(history[-1]["status"]):
        return
    run_at = now.astimezone(UTC)
    previous = _read_progress(output_dir)
    if previous is not None:
        report = {**previous, **json_safe({"status": "error", "reason": reason, "run_at": run_at})}
    else:
        report = _fresh_report(
            status="error",
            reason=reason,
            through=None,
            segment=None,
            gap=None,
            commits=[],
            frozen_check="not checked",
            run_at=run_at,
        )
    _write_progress(output_dir, report)
    _append_history(
        output_dir,
        {
            "run_at": run_at,
            "through": report["through"],
            "status": "error",
            "reason": reason,
            "gap": None,
            "commit": None,
        },
    )


TITLE = "SILVR forward test"
OUTPUT_DIR = Path("reports") / "trend_ensemble_forward"  # under the current directory; there is no option
FIRST_REPORT_DATE = "2026-12-01"  # the first UTC month (November 2026) closes then


def _dollars(amount: float) -> str:
    cents = round(amount, 2)
    return f"{'-' if cents < 0 else ''}${abs(cents):.2f}"


def summary_line(progress: Mapping[str, Any]) -> str:
    """One short line for the monthly toast: the net so far while running, otherwise the status itself."""
    status = progress["status"]
    if status == "error":
        return f"{TITLE} error: {progress['reason']}"
    if status == _INCOMPLETE:
        return f"{TITLE}: {_INCOMPLETE}: {progress['reason']}"
    if status == "running":
        month = datetime.fromisoformat(progress["through"]).strftime("%b %Y")
        return f"{TITLE}, {month}: net {_dollars(progress['net'])} so far (progress only)"
    return f"{TITLE}: {status}"


def _toast(line: str) -> None:
    """Print the toast as one line: any newline or tab in a reason would otherwise split it."""
    print(f"TOAST: {' '.join(line.split())}")


def _run_cli(args: argparse.Namespace, now: datetime) -> int:
    """Do what the arguments ask and print the toast line last; returns the exit code (0, 1 or 2)."""
    if args.void is not None:
        try:
            entry = record_void(OUTPUT_DIR, args.void, now)
        except ValueError as exc:  # the test has already ended; nothing was written
            print(f"error: {exc}")
            _toast(summary_line({"status": "error", "reason": str(exc)}))
            return 2
        _toast(summary_line(entry))
        return 0
    problems = download_new_data(args.data_root, now) if args.download else None
    report = run_progress(
        repo_root=Path.cwd(),
        data_root=args.data_root,
        output_dir=OUTPUT_DIR,
        now=now,
        download_problems=problems,
    )
    for problem in problems or []:
        print(f"download problem: {problem}")
    if report is None:
        _toast(f"{TITLE}: nothing to report until {FIRST_REPORT_DATE}")
        return 0
    _toast(summary_line(report))
    return 1 if report["status"] == "error" else 0


def main(argv: list[str] | None = None) -> int:
    """Run the monthly forward-test step. Exit 0: reported (or nothing yet); 1: error; 2: bad arguments."""
    parser = argparse.ArgumentParser(prog="python -m silvr.backtest.trend_forward", description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--download", action="store_true", help="download the newly closed months first")
    parser.add_argument("--void", metavar="REASON", help="end the test as void with this reason, then exit")
    for stream in (sys.stdout, sys.stderr):  # a redirected cp1252 stream must never lose the toast line
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    try:
        args = parser.parse_args(argv)
        if args.void is not None and not args.void.strip():
            parser.error("--void needs a reason")
    except SystemExit as exc:
        if not exc.code:  # --help
            raise
        _toast(f"{TITLE} error: bad command line arguments (see the message above)")
        return 2
    now = datetime.now(UTC)
    try:
        return _run_cli(args, now)
    except Exception as exc:  # the toast must still say something; the error report is best effort
        reason = f"{type(exc).__name__}: {exc}"
        traceback.print_exc(file=sys.stderr)
        try:
            record_error(OUTPUT_DIR, reason, now)
        except Exception as write_exc:
            print(f"could not write the error report: {write_exc}")
        _toast(summary_line({"status": "error", "reason": reason}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
