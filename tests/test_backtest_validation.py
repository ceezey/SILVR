import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from silver_bot.backtest import BacktestValidationSuite, run_backtest
from silver_bot.backtest.criteria import (
    FAIL,
    PASS,
    PASS_PENDING_OWNER_INPUT,
    combine_verdicts,
    evaluate_evidence,
)
from silver_bot.backtest.validation import monte_carlo_r
from silver_bot.config import AppConfig, TradingMode
from silver_bot.models import Candle


def candles(count: int) -> list[Candle]:
    start = datetime(2026, 1, 2, 14, 0, tzinfo=UTC)
    return [
        Candle(
            symbol="BTCUSDT",
            timeframe="1m",
            open_time=start + timedelta(minutes=index),
            close_time=start + timedelta(minutes=index + 1),
            open=100,
            high=102,
            low=98,
            close=101,
            volume=1000,
        )
        for index in range(count)
    ]


def backtest_settings() -> AppConfig:
    return AppConfig(mode=TradingMode.BACKTEST, paper_trading=False)


def good_metrics(**overrides) -> dict:
    values = {"profit_factor": 1.5, "expectancy": 10.0, "max_drawdown_percent": 0.05, "total_trades": 40}
    values.update(overrides)
    return values


def checks_by_name(result: dict) -> dict:
    return {check["name"]: check for check in result["checks"]}


def test_walk_forward_windows_are_consecutive_and_cover_everything() -> None:
    data = candles(10)

    windows = BacktestValidationSuite().walk_forward_windows(list(reversed(data)), windows=3)

    assert [len(window) for window in windows] == [3, 3, 4]
    assert [candle for window in windows for candle in window] == data


def test_walk_forward_rejects_zero_windows_and_skips_tiny_input() -> None:
    suite = BacktestValidationSuite()

    with pytest.raises(ValueError, match="windows must be at least 1"):
        suite.walk_forward_windows(candles(5), windows=0)
    assert suite.walk_forward_windows(candles(2), windows=4) == []


def test_monte_carlo_is_deterministic_for_a_seed() -> None:
    trades = [2.0, -1.0, -1.0, 2.0, -1.0, 3.0]

    first = monte_carlo_r(trades, runs=200, seed=11)
    second = monte_carlo_r(trades, runs=200, seed=11)

    assert first == second
    assert first["trades"] == 6
    assert first["final_r"]["p5"] <= first["final_r"]["p50"] <= first["final_r"]["p95"]
    assert first["max_drawdown_r"]["p50"] >= 0
    assert 0 <= first["probability_final_r_not_positive"] <= 1


def test_monte_carlo_with_no_trades_reports_nothing() -> None:
    result = monte_carlo_r([], runs=10)

    assert result["trades"] == 0
    assert result["final_r"] is None


def test_monte_carlo_rejects_zero_runs() -> None:
    with pytest.raises(ValueError, match="runs must be at least 1"):
        monte_carlo_r([1.0], runs=0)


def test_evidence_without_owner_inputs_is_pending() -> None:
    result = evaluate_evidence(good_metrics(), slippage_bps=5.0, spread_bps=3.0)

    checks = checks_by_name(result)
    assert result["verdict"] == PASS_PENDING_OWNER_INPUT
    assert checks["profit_factor"]["passed"] is True
    assert checks["max_drawdown"]["passed"] is None
    assert checks["max_drawdown"]["reason"] == "Owner input required (OI-3)"
    assert checks["min_trades"]["reason"] == "Owner input required (OI-9)"


def test_evidence_passes_with_owner_inputs_met() -> None:
    result = evaluate_evidence(
        good_metrics(),
        slippage_bps=5.0,
        spread_bps=3.0,
        max_drawdown_percent=0.1,
        min_trades=30,
    )

    assert result["verdict"] == PASS


@pytest.mark.parametrize(
    ("metrics", "costs", "failed"),
    [
        (good_metrics(profit_factor=1.19), (5.0, 3.0), "profit_factor"),
        (good_metrics(expectancy=0.0), (5.0, 3.0), "expectancy"),
        (good_metrics(), (0.0, 3.0), "costs_non_zero"),
        (good_metrics(), (5.0, 0.0), "costs_non_zero"),
        ({}, (5.0, 3.0), "profit_factor"),
    ],
)
def test_evidence_fails_on_brd_thresholds(metrics: dict, costs: tuple, failed: str) -> None:
    result = evaluate_evidence(metrics, slippage_bps=costs[0], spread_bps=costs[1])

    assert result["verdict"] == FAIL
    assert checks_by_name(result)[failed]["passed"] is False


def test_evidence_fails_on_owner_thresholds() -> None:
    result = evaluate_evidence(
        good_metrics(max_drawdown_percent=0.2, total_trades=10),
        slippage_bps=5.0,
        spread_bps=3.0,
        max_drawdown_percent=0.1,
        min_trades=30,
    )

    checks = checks_by_name(result)
    assert result["verdict"] == FAIL
    assert checks["max_drawdown"]["passed"] is False
    assert checks["min_trades"]["passed"] is False


def test_infinite_profit_factor_passes() -> None:
    result = evaluate_evidence(good_metrics(profit_factor=float("inf")), slippage_bps=5.0, spread_bps=3.0)

    assert checks_by_name(result)["profit_factor"]["passed"] is True


def test_combine_verdicts_keeps_the_weakest() -> None:
    assert combine_verdicts(PASS, FAIL) == FAIL
    assert combine_verdicts(PASS, PASS_PENDING_OWNER_INPUT) == PASS_PENDING_OWNER_INPUT
    assert combine_verdicts(PASS, PASS) == PASS


def test_out_of_sample_report_has_walk_forward_monte_carlo_and_criteria(tmp_path: Path) -> None:
    data = candles(50)
    summary = run_backtest(backtest_settings(), data, tmp_path, inputs={})

    oos = json.loads(summary.report_paths["out_of_sample_validation_report"].read_text(encoding="utf-8"))

    windows = oos["walk_forward"]["windows"]
    assert oos["walk_forward"]["span"] == "training_and_validation"
    assert [window["candles"] for window in windows] == [10, 10, 10, 10]
    # Walk-forward never reaches the final test set (the last 10 candles).
    assert windows[-1]["end"] < oos["segments"]["final_test"]["start"]
    assert oos["monte_carlo"]["source"] == "full_period_trades"
    assert oos["monte_carlo"]["seed"] == 7
    # These synthetic candles never trade, so both criteria sets fail.
    assert oos["criteria"]["verdict"] == FAIL
    assert oos["criteria"]["final_test"]["verdict"] == FAIL
    assert oos["segments"]["training"]["criteria"]["verdict"] == FAIL
