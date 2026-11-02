"""Pooled promotion gate: one verdict over several symbols' backtests of the same strategy.

Merges the per-symbol out-of-sample reports into one report of the same shape and runs the promotion gate
on it, so the thresholds, the look counting and the audit log are the gate's own. Like the gate, it only
reports: it unlocks nothing.

Exit codes are the gate's; 2 also covers reports that do not belong together.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from silver_bot.backtest import gate
from silver_bot.backtest.gate import RERUN_HINT, GateInputError
from silver_bot.backtest.metrics import calculate_metrics
from silver_bot.backtest.models import EquityPoint
from silver_bot.backtest.reporting import json_safe

SEGMENTS = ("training", "validation", "final_test")
FRACTIONS = {"training": 0.6, "validation": 0.2, "final_test": 0.2}
# The symbol list fixed before any run (spec MS-1, section 5). Any other set is refused, so no symbol can be
# dropped or added after a result has been seen.
FROZEN_SYMBOLS = {
    "top_down_ob_v4": (
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "AVAXUSDT",
        "LINKUSDT", "DOTUSDT", "LTCUSDT", "TRXUSDT", "ATOMUSDT", "NEARUSDT", "BCHUSDT",
    ),
}


@dataclass(frozen=True, slots=True)
class _Trade:
    """One row of a segment's trade list: the fields `calculate_metrics` reads, and the two times."""

    entry_time: str
    exit_time: str
    realized_r: float
    realized_pnl: float
    fees: float
    funding: float
    session_name: str


def pool(reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return one out-of-sample report over the union of the reports' trades, segment by segment."""

    if not reports:
        raise GateInputError("no reports to pool")
    strategies = {report.get("strategy") for report in reports}
    if len(strategies) != 1:
        raise GateInputError(f"the reports mix strategies: {', '.join(sorted(map(str, strategies)))}")
    strategy = strategies.pop()
    symbols = [report.get("symbol") for report in reports]
    if None in symbols or len(set(symbols)) != len(symbols):
        raise GateInputError(f"each report needs its own symbol, got {symbols}; {RERUN_HINT}")
    if sorted(symbols) != sorted(FROZEN_SYMBOLS.get(strategy, ())):
        raise GateInputError(f"the symbols are not the frozen list for {strategy}: {symbols}")
    for report in reports:
        untouched = report.get("parameters_tuned") is False and report.get("method") == "chronological_split"
        if not untouched or report.get("fractions") != FRACTIONS:
            raise GateInputError(f"{report['symbol']} is not an untuned 60/20/20 chronological split; {RERUN_HINT}")
    return {
        "method": "pooled_chronological_split",
        "strategy": strategy,
        "symbols": symbols,
        "segments": {name: _pool_segment([gate._segment(report, name) for report in reports], name) for name in SEGMENTS},
    }


def _pool_segment(segments: list[Mapping[str, Any]], name: str) -> dict[str, Any]:
    ranges = {(segment.get("start"), segment.get("end")) for segment in segments}
    if len(ranges) != 1:
        raise GateInputError(f"segment '{name}' covers different dates across the reports")
    balances = {gate._number(segment.get("initial_balance"), f"{name}.initial_balance") for segment in segments}
    if len(balances) != 1:
        raise GateInputError(f"segment '{name}' starts the accounts with different balances")
    balance = balances.pop()  # one account's: the 15 accounts' P&L lands on it as if it took every signal (MS-5)
    trades: list[_Trade] = []
    candles = 0
    trips = 0
    for segment in segments:
        rows = segment.get("trades")
        if not isinstance(rows, list):
            raise GateInputError(f"segment '{name}' has no trade list; {RERUN_HINT}")
        try:
            trades += [_Trade(**row) for row in rows]
        except TypeError as exc:
            raise GateInputError(f"segment '{name}' has a malformed trade ({exc}); {RERUN_HINT}") from exc
        candles += int(gate._number(segment.get("candles"), f"{name}.candles"))
        kill_switch = segment.get("kill_switch")
        trips += int(kill_switch.get("trips") or 0) if isinstance(kill_switch, Mapping) else 0
    start, end = ranges.pop()
    return {
        "candles": candles,
        "start": start,
        "end": end,
        "initial_balance": balance,
        "kill_switch": {"trips": trips},
        "metrics": _metrics(trades, balance) if trades else None,
    }


def _metrics(trades: list[_Trade], balance: float) -> dict[str, Any]:
    """The pooled metrics: one symbol's formulas, over the merged trades.

    Drawdown and return run on the merged realized P&L in exit-time order against one account's balance, as if
    one account took every symbol's signals (MS-5). Summed balances would dilute the gate's drawdown limit.
    The real-edge t-stat is the lower of the trade t and the t of R summed per UTC entry day (MS-4),
    because setups on correlated symbols on the same day are not independent evidence.
    """

    trades = sorted(trades, key=lambda trade: datetime.fromisoformat(trade.exit_time))
    curve = []
    equity = peak = balance
    for trade in trades:
        equity += trade.realized_pnl
        peak = max(peak, equity)
        curve.append(EquityPoint(datetime.fromisoformat(trade.exit_time), equity, equity - balance, peak - equity))
    metrics = calculate_metrics(trades, curve, initial_balance=balance)  # type: ignore[arg-type]
    trade_t = metrics["r_t_stat"]
    day_t = _day_t_stat(trades)
    metrics.update(trade_r_t_stat=trade_t, day_r_t_stat=day_t, r_t_stat=min(trade_t, day_t))
    return metrics


def _day_t_stat(trades: list[_Trade]) -> float:
    """t-stat of R summed per UTC entry day; 0.0 below two days or with no spread, as for trades."""

    days: dict[Any, float] = defaultdict(float)
    for trade in trades:
        days[datetime.fromisoformat(trade.entry_time).astimezone(UTC).date()] += trade.realized_r
    sums = list(days.values())
    if len(sums) < 2:
        return 0.0
    spread = statistics.stdev(sums)
    return statistics.fmean(sums) / (spread / math.sqrt(len(sums))) if spread else 0.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pool several symbols' out-of-sample reports and run the promotion gate on them. Unlocks nothing."
    )
    parser.add_argument("--report", action="append", required=True, help="one symbol's report JSON; repeat per symbol")
    parser.add_argument("--output-dir", required=True, help="for the pooled report, the verdict and the gate's look log")
    args = parser.parse_args(argv)
    sources = [Path(path) for path in args.report]
    output = Path(args.output_dir) / Path(gate.DEFAULT_REPORT).name
    try:
        if output.resolve() in {source.resolve() for source in sources}:
            raise GateInputError(f"{output} is one of the input reports; choose another --output-dir")
        pooled = pool([gate._load(source) for source in sources])
        segments = pooled["segments"]
        data_range = {"data_start": segments["training"]["start"], "data_end": segments["final_test"]["end"]}
        if not gate._count_looks(output.parent / gate.LOG_NAME, data_range):
            # Without the earlier runs on this data range the gate would count look 1 and lower its bar (MS-6).
            raise GateInputError(f"{output.parent / gate.LOG_NAME} has no earlier run on this data range; carry it over")
    except GateInputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    pooled["sources"] = [
        {"report": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()} for source in sources
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(json_safe(pooled), indent=2), encoding="utf-8")
    return gate.main(["--report", str(output)])


if __name__ == "__main__":
    raise SystemExit(main())
