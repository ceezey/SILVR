"""Settings-driven backtest run that writes the readiness evidence reports."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import silver_bot
from silver_bot.backtest.engine import BacktestEngine
from silver_bot.backtest.models import BacktestConfig, BacktestResult
from silver_bot.backtest.reporting import _json_safe
from silver_bot.backtest.validation import BacktestValidationSuite
from silver_bot.config import AppConfig
from silver_bot.ml import MLFilterConfig
from silver_bot.models import Candle
from silver_bot.risk import build_risk_config

TRAINING_FRACTION = 0.6
VALIDATION_FRACTION = 0.2
KILL_SWITCH_FILENAME = "KILL_SWITCH"


@dataclass(frozen=True, slots=True)
class BacktestRunSummary:
    """Where a backtest run wrote its reports."""

    candles: int
    report_paths: dict[str, Path]


def build_backtest_config(
    config: AppConfig,
    *,
    export_dir: Path | None,
    kill_switch_path: Path,
) -> BacktestConfig:
    """Return a backtest config whose risk and ML settings come from AppConfig.

    `kill_switch_path` is the run's simulated kill switch. It replaces the real
    path, so the simulation halts on its own trips and never touches the real
    kill-switch file.
    """

    return BacktestConfig(
        risk=replace(build_risk_config(config), kill_switch_path=kill_switch_path),
        ml_filter=MLFilterConfig(
            enabled=config.ml_filter_enabled,
            registry_path=config.ml_registry_path,
            min_probability=config.ml_min_probability,
            reduce_risk_threshold=config.ml_reduce_risk_threshold,
        ),
        export_dir=export_dir,
    )


def run_backtest(
    config: AppConfig,
    candles: Sequence[Candle],
    output_dir: str | Path,
    *,
    inputs: Mapping[str, Any],
) -> BacktestRunSummary:
    """Run the full-period backtest and a chronological out-of-sample split."""

    if not candles:
        raise ValueError("run_backtest needs at least one candle")
    directory = Path(output_dir)
    ordered = sorted(candles, key=lambda candle: candle.open_time)

    full, full_trip, full_config = _simulate(config, ordered, export_dir=directory)

    split = BacktestValidationSuite().chronological_split(
        ordered,
        training_fraction=TRAINING_FRACTION,
        validation_fraction=VALIDATION_FRACTION,
    )
    oos_path = directory / "out_of_sample_validation_report.json"
    _write_json(
        oos_path,
        {
            "method": "chronological_split",
            "fractions": {
                "training": TRAINING_FRACTION,
                "validation": VALIDATION_FRACTION,
                "final_test": round(1 - TRAINING_FRACTION - VALIDATION_FRACTION, 10),
            },
            "parameters_tuned": False,
            "segments": {
                "training": _segment(config, split.training),
                "validation": _segment(config, split.validation),
                "final_test": _segment(config, split.final_test),
            },
        },
    )

    run_path = directory / "backtest_run.json"
    _write_json(
        run_path,
        {
            "inputs": dict(inputs),
            "symbol": config.symbol,
            "timeframe": config.timeframe,
            "candles": len(ordered),
            "first_open_time": ordered[0].open_time.isoformat(),
            "last_open_time": ordered[-1].open_time.isoformat(),
            "slippage_bps": full_config.slippage_bps,
            "spread_bps": full_config.spread_bps,
            "maker_fee": full_config.maker_fee,
            "taker_fee": full_config.taker_fee,
            "ml_filter_enabled": full_config.ml_filter.enabled,
            "risk_per_trade": full_config.risk.risk_per_trade,
            "kill_switch": {"mode": "simulated_per_run", **full_trip},
            "package_version": silver_bot.__version__,
        },
    )

    paths = dict(full.export_paths)
    paths["out_of_sample_validation_report"] = oos_path
    paths["backtest_run"] = run_path
    return BacktestRunSummary(candles=len(ordered), report_paths=paths)


def _simulate(
    config: AppConfig,
    candles: list[Candle],
    *,
    export_dir: Path | None,
) -> tuple[BacktestResult, dict[str, Any], BacktestConfig]:
    """Run one engine with its own simulated kill switch.

    Returns the result, the trip record and the config the engine ran with.
    """

    with tempfile.TemporaryDirectory() as scratch:
        kill_switch_path = Path(scratch) / KILL_SWITCH_FILENAME
        backtest_config = build_backtest_config(config, export_dir=export_dir, kill_switch_path=kill_switch_path)
        result = BacktestEngine(config=backtest_config).run(candles)
        return result, _read_trip(kill_switch_path), backtest_config


def _read_trip(path: Path) -> dict[str, Any]:
    """Describe a simulated kill-switch file: whether it tripped, and why."""

    if not path.exists():
        return {"tripped": False, "reason": None, "tripped_at": None}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return {"tripped": True, "reason": payload.get("reason"), "tripped_at": payload.get("tripped_at")}


def _segment(config: AppConfig, candles: list[Candle]) -> dict[str, Any]:
    if not candles:
        return {"candles": 0, "start": None, "end": None, "metrics": None, "kill_switch": None}
    result, trip, _ = _simulate(config, candles, export_dir=None)
    return {
        "candles": len(candles),
        "start": candles[0].open_time.isoformat(),
        "end": candles[-1].open_time.isoformat(),
        "metrics": result.metrics,
        "kill_switch": trip,
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(dict(payload)), indent=2, sort_keys=True), encoding="utf-8")
