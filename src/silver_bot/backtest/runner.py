"""Settings-driven backtest run that writes the readiness evidence reports."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import silver_bot
from silver_bot.backtest.engine import BacktestEngine
from silver_bot.backtest.criteria import combine_verdicts, evaluate_evidence
from silver_bot.backtest.models import BacktestConfig, BacktestResult
from silver_bot.backtest.reporting import json_safe
from silver_bot.backtest.sim_kill_switch import SimulatedKillSwitch
from silver_bot.backtest.top_down_engine import TopDownBacktestEngine
from silver_bot.backtest.validation import BacktestValidationSuite, monte_carlo_r
from silver_bot.config import AppConfig
from silver_bot.data.funding import FundingSchedule
from silver_bot.ml import MLFilterConfig
from silver_bot.models import Candle
from silver_bot.monitoring import StructuredAuditLogger
from silver_bot.risk import RiskManagementEngine, build_risk_config

TRAINING_FRACTION = 0.6
VALIDATION_FRACTION = 0.2
STRATEGIES = ("silver_bullet", "top_down_ob")
WALK_FORWARD_WINDOWS = 4
MONTE_CARLO_RUNS = 1000
MONTE_CARLO_SEED = 7


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
        ml_filter=build_ml_filter_config(config),
        export_dir=export_dir,
    )


def build_ml_filter_config(config: AppConfig) -> MLFilterConfig:
    """Return the ML filter settings from AppConfig (shared by backtest and paper)."""

    return MLFilterConfig(
        enabled=config.ml_filter_enabled,
        registry_path=config.ml_registry_path,
        min_probability=config.ml_min_probability,
        reduce_risk_threshold=config.ml_reduce_risk_threshold,
    )


def run_backtest(
    config: AppConfig,
    candles: Sequence[Candle],
    output_dir: str | Path,
    *,
    inputs: Mapping[str, Any],
    strategy: str = "silver_bullet",
    funding: FundingSchedule | None = None,
) -> BacktestRunSummary:
    """Run the full-period backtest and a chronological out-of-sample split.

    `top_down_ob` needs `funding`. Its full run has no warm-up; each segment is warmed up on every
    candle before it, so the strategy has history without trading on it. `silver_bullet` ignores
    `funding` and keeps its cold start per segment.
    """

    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}; expected one of {', '.join(STRATEGIES)}")
    if strategy == "top_down_ob" and funding is None:
        raise ValueError("strategy top_down_ob needs funding data")
    if strategy == "silver_bullet":
        funding = None
    if not candles:
        raise ValueError("run_backtest needs at least one candle")
    directory = Path(output_dir)
    ordered = sorted(candles, key=lambda candle: candle.open_time)

    full, full_kill_switch, full_config = _simulate(config, ordered, export_dir=directory, funding=funding)

    suite = BacktestValidationSuite()
    split = suite.chronological_split(
        ordered,
        training_fraction=TRAINING_FRACTION,
        validation_fraction=VALIDATION_FRACTION,
    )
    full_criteria = _criteria(full.metrics, full_config)
    training = _segment(config, split.training, funding, ordered)
    validation = _segment(config, split.validation, funding, ordered)
    final_test = _segment(config, split.final_test, funding, ordered)
    # Walk-forward covers the training and validation span only, so the final
    # test set is evaluated exactly once, in its own segment above.
    research = [*split.training, *split.validation]
    windows = suite.walk_forward_windows(research, windows=WALK_FORWARD_WINDOWS)
    walk_forward = [_segment(config, window, funding, ordered) for window in windows]
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
            "strategy": strategy,
            "segments": {
                "training": training,
                "validation": validation,
                "final_test": final_test,
            },
            "walk_forward": {"span": "training_and_validation", "windows": walk_forward},
            "monte_carlo": {
                "source": "full_period_trades",
                "note": "includes final-test trades; do not tune on it",
                **monte_carlo_r(
                    [trade.realized_r for trade in full.trades],
                    runs=MONTE_CARLO_RUNS,
                    seed=MONTE_CARLO_SEED,
                ),
            },
            "criteria": {
                "note": "not promotion evidence; see promotion_gate",
                "verdict": combine_verdicts(full_criteria["verdict"], final_test["criteria"]["verdict"]),
                "full_period": full_criteria,
                "final_test": final_test["criteria"],
            },
        },
    )

    run_path = directory / "backtest_run.json"
    _write_json(
        run_path,
        {
            "inputs": dict(inputs),
            "strategy": strategy,
            "funding_file": inputs.get("funding_file") if funding is not None else None,
            "symbol": config.symbol,
            "timeframe": config.timeframe,
            "candles": len(ordered),
            "first_open_time": ordered[0].open_time.isoformat(),
            "last_open_time": ordered[-1].open_time.isoformat(),
            "slippage_bps": full_config.slippage_bps,
            "spread_bps": full_config.spread_bps,
            "maker_fee": full_config.maker_fee,
            "taker_fee": full_config.taker_fee,
            # The top-down engine applies no ML filter.
            "ml_filter_enabled": full_config.ml_filter.enabled and strategy == "silver_bullet",
            "risk_per_trade": full_config.risk.risk_per_trade,
            "kill_switch": full_kill_switch,
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
    funding: FundingSchedule | None,
    warmup: Sequence[Candle] = (),
) -> tuple[BacktestResult, dict[str, Any], BacktestConfig]:
    """Run one engine with its own simulated kill switch (and, for top-down, its own fresh strategy).

    Returns the result, the kill-switch report (trip count and log) and the
    config the engine ran with.
    """

    with SimulatedKillSwitch() as kill_switch:
        backtest_config = build_backtest_config(config, export_dir=export_dir, kill_switch_path=kill_switch.path)
        risk_engine = RiskManagementEngine(backtest_config.risk, kill_switch=kill_switch)
        if funding is None:
            result = BacktestEngine(
                config=backtest_config,
                risk_engine=risk_engine,
                audit_logger=StructuredAuditLogger(retain_events=False),
            ).run(candles)
        else:
            result = TopDownBacktestEngine(
                config=backtest_config, risk_engine=risk_engine, funding=funding
            ).run(candles, warmup=warmup)
        return result, kill_switch.report(), backtest_config


def _segment(
    config: AppConfig, candles: list[Candle], funding: FundingSchedule | None, ordered: list[Candle]
) -> dict[str, Any]:
    if not candles:
        # No run means no metrics; costs are the BacktestConfig defaults, which
        # build_backtest_config never changes.
        criteria = _criteria({}, BacktestConfig())
        return {"candles": 0, "start": None, "end": None, "metrics": None, "kill_switch": None, "criteria": criteria}
    # `candles` is a slice of `ordered`; everything before its first candle is warm-up history.
    warmup = ordered[: ordered.index(candles[0])] if funding is not None else ()
    result, kill_switch, backtest_config = _simulate(config, candles, export_dir=None, funding=funding, warmup=warmup)
    return {
        "candles": len(candles),
        "start": candles[0].open_time.isoformat(),
        "end": candles[-1].open_time.isoformat(),
        "metrics": result.metrics,
        "kill_switch": kill_switch,
        "criteria": _criteria(result.metrics, backtest_config),
    }


def _criteria(metrics: Mapping[str, Any], backtest_config: BacktestConfig) -> dict[str, Any]:
    return evaluate_evidence(
        metrics,
        slippage_bps=backtest_config.slippage_bps,
        spread_bps=backtest_config.spread_bps,
    )


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(dict(payload)), indent=2, sort_keys=True), encoding="utf-8")
