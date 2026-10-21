"""Phase 2 promotion gate.

Reads the backtest's out-of-sample report and prints PASS/FAIL for each
promotion criterion. It only reports: it does not unlock demo mode, write
readiness evidence or change any configuration.

Exit codes: 0 every criterion passes (WARN counts as a pass), 1 any criterion
fails, 2 the report is missing, empty or malformed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

MIN_TRADES = 100
MIN_T_STAT = 2.0
MIN_PROFIT_FACTOR = 1.5
WARN_PROFIT_FACTOR = 3.0
MIN_REALIZED_RR = 1.5
MAX_DRAWDOWN_PERCENT = 0.10
MIN_RETURN_TO_DRAWDOWN = 2.0
MIN_OOS_EFFICIENCY = 0.5

DEFAULT_REPORT = "reports/out_of_sample_validation_report.json"
OUTPUT_NAME = "promotion_gate.json"
LOG_NAME = "promotion_gate_log.jsonl"
RERUN_HINT = "re-run the backtest to regenerate the report"
REMINDER = (
    "No peeking: strategy settings were frozen before this final test; "
    "every extra variant raises the bar (Deflated Sharpe Ratio)."
)

_REQUIRED_FINAL_KEYS = (
    "average_r",
    "r_t_stat",
    "profit_factor",
    "realized_rr",
    "max_drawdown_percent",
    "return_to_drawdown",
)

Result = Literal["PASS", "FAIL", "WARN"]


class GateInputError(ValueError):
    """The report lacks a segment, a metric or a value the gate needs."""


@dataclass(frozen=True)
class CriterionResult:
    number: int
    name: str
    threshold: str
    actual: str
    result: Result


@dataclass(frozen=True)
class GateVerdict:
    criteria: list[CriterionResult]
    info: dict[str, Any]
    passed: bool


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise GateInputError(f"{label} is not a number; {RERUN_HINT}")
    if isinstance(value, str) and value.strip().lower() in {"inf", "+inf", "-inf"}:
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    raise GateInputError(f"{label} is not a number; {RERUN_HINT}")


def _segment(report: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    segments = report.get("segments")
    segment = segments.get(name) if isinstance(segments, Mapping) else None
    if not isinstance(segment, Mapping):
        raise GateInputError(f"segment '{name}' is missing from the report; {RERUN_HINT}")
    return segment


def _metrics(segment: Mapping[str, Any], name: str, required: tuple[str, ...]) -> Mapping[str, Any] | None:
    """Return the metrics, or None when the segment has no trades."""
    metrics = segment.get("metrics")
    if metrics is None:
        return None
    if not isinstance(metrics, Mapping):
        raise GateInputError(f"segment '{name}' metrics are malformed; {RERUN_HINT}")
    trades = _number(metrics.get("total_trades"), f"{name}.total_trades")
    if trades <= 0:
        return None
    missing = [key for key in required if key not in metrics]
    if missing:
        raise GateInputError(f"segment '{name}' metrics lack {', '.join(missing)}; {RERUN_HINT}")
    return metrics


def _fmt(value: float) -> str:
    return "inf" if value == float("inf") else f"{value:.4g}"


def evaluate_gate(report: Mapping[str, Any]) -> GateVerdict:
    training = _segment(report, "training")
    final = _segment(report, "final_test")
    _segment(report, "validation")

    final_metrics = _metrics(final, "final_test", _REQUIRED_FINAL_KEYS)
    training_metrics = _metrics(training, "training", ("average_r",))

    candles = 0
    for name in ("training", "validation", "final_test"):
        candles += int(_number(_segment(report, name).get("candles"), f"{name}.candles"))
    kill_switch = final.get("kill_switch")
    trips = kill_switch.get("trips") if isinstance(kill_switch, Mapping) else None
    info = {
        "data_start": training.get("start"),
        "data_end": final.get("end"),
        "candles": candles,
        "final_test_kill_switch_trips": trips,
    }

    def criterion(number: int, name: str, threshold: str, actual: str, ok: bool, warn: bool = False) -> CriterionResult:
        result: Result = "FAIL" if not ok else ("WARN" if warn else "PASS")
        return CriterionResult(number, name, threshold, actual, result)

    names = {
        1: ("Enough trades", f">= {MIN_TRADES}"),
        2: ("Real edge", f"avg R > 0, t >= {MIN_T_STAT}"),
        3: ("Profit factor", f">= {MIN_PROFIT_FACTOR} (warn > {WARN_PROFIT_FACTOR})"),
        4: ("Realized reward:risk", f">= {MIN_REALIZED_RR}"),
        5: ("Drawdown", f"<= {MAX_DRAWDOWN_PERCENT}, return/dd >= {MIN_RETURN_TO_DRAWDOWN}"),
        6: ("Out-of-sample efficiency", f"final avg R >= {MIN_OOS_EFFICIENCY} x training, training > 0"),
    }

    if final_metrics is None:
        criteria = [
            CriterionResult(number, name, threshold, "no trades in final test", "FAIL")
            for number, (name, threshold) in names.items()
        ]
        return GateVerdict(criteria=criteria, info=info, passed=False)

    trades = _number(final_metrics["total_trades"], "final_test.total_trades")
    average_r = _number(final_metrics["average_r"], "final_test.average_r")
    t_stat = _number(final_metrics["r_t_stat"], "final_test.r_t_stat")
    profit_factor = _number(final_metrics["profit_factor"], "final_test.profit_factor")
    realized_rr = _number(final_metrics["realized_rr"], "final_test.realized_rr")
    drawdown = _number(final_metrics["max_drawdown_percent"], "final_test.max_drawdown_percent")
    ret_dd = _number(final_metrics["return_to_drawdown"], "final_test.return_to_drawdown")
    training_r = _number(training_metrics["average_r"], "training.average_r") if training_metrics else None

    if training_r is None:
        efficiency_actual, efficiency_ok = "no training trades", False
    else:
        efficiency_ok = training_r > 0 and average_r >= MIN_OOS_EFFICIENCY * training_r
        efficiency_actual = f"final {_fmt(average_r)} vs training {_fmt(training_r)}"

    criteria = [
        criterion(1, *names[1], f"{int(trades)}", trades >= MIN_TRADES),
        criterion(2, *names[2], f"avg R {_fmt(average_r)}, t {_fmt(t_stat)}", average_r > 0 and t_stat >= MIN_T_STAT),
        criterion(
            3,
            *names[3],
            _fmt(profit_factor),
            profit_factor >= MIN_PROFIT_FACTOR,
            warn=profit_factor > WARN_PROFIT_FACTOR,
        ),
        criterion(4, *names[4], _fmt(realized_rr), realized_rr >= MIN_REALIZED_RR),
        criterion(
            5,
            *names[5],
            f"dd {_fmt(drawdown)}, return/dd {_fmt(ret_dd)}",
            drawdown <= MAX_DRAWDOWN_PERCENT and ret_dd >= MIN_RETURN_TO_DRAWDOWN,
        ),
        criterion(6, *names[6], efficiency_actual, efficiency_ok),
    ]
    return GateVerdict(criteria=criteria, info=info, passed=all(c.result != "FAIL" for c in criteria))


def _render(verdict: GateVerdict) -> str:
    rows = [("#", "Criterion", "Threshold", "Actual", "Result")]
    rows += [(str(c.number), c.name, c.threshold, c.actual, c.result) for c in verdict.criteria]
    widths = [max(len(row[i]) for row in rows) for i in range(4)]
    lines = [
        "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row[:4])) + "  " + row[4] for row in rows
    ]
    lines.append("")
    lines += [f"{key}: {value}" for key, value in verdict.info.items()]
    lines.append("")
    lines.append(f"7  {REMINDER}")
    lines.append(f"GATE: {'PASS' if verdict.passed else 'FAIL'}")
    return "\n".join(lines)


def _load(path: Path) -> Mapping[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GateInputError(f"cannot read {path}: {exc.strerror or exc}; {RERUN_HINT}") from exc
    if not text.strip():
        raise GateInputError(f"{path} is empty; {RERUN_HINT}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GateInputError(f"{path} is not valid JSON ({exc}); {RERUN_HINT}") from exc
    if not isinstance(data, Mapping):
        raise GateInputError(f"{path} is not a JSON object; {RERUN_HINT}")
    return data


def _log_run(path: Path, verdict: GateVerdict) -> int:
    """Append one audit line for this run and return how many runs saw the same data range.

    Repeated looks at the final test raise the bar (criterion 7), so each run is
    recorded with a hash of the exact report it judged.
    """

    info = verdict.info
    entry = {
        "run_at": datetime.now(UTC).isoformat(),
        "report": str(path),
        "report_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "data_start": info["data_start"],
        "data_end": info["data_end"],
        "candles": info["candles"],
        "passed": verdict.passed,
    }
    log_path = path.parent / LOG_NAME
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
    runs = 0
    for line in log_path.read_text(encoding="utf-8").splitlines():
        try:
            past = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(past, Mapping) and (past.get("data_start"), past.get("data_end")) == (
            entry["data_start"],
            entry["data_end"],
        ):
            runs += 1
    return runs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report the phase 2 promotion criteria. Unlocks nothing.")
    parser.add_argument("--report", default=DEFAULT_REPORT, help="out-of-sample validation report JSON")
    args = parser.parse_args(argv)
    path = Path(args.report)
    try:
        verdict = evaluate_gate(_load(path))
    except GateInputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(_render(verdict))
    payload = {
        "report": str(path),
        "passed": verdict.passed,
        "criteria": [asdict(c) for c in verdict.criteria],
        "info": verdict.info,
        "reminder": f"7  {REMINDER}",
    }
    (path.parent / OUTPUT_NAME).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"gate runs on this data range: {_log_run(path, verdict)}")
    return 0 if verdict.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
