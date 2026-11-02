"""Pooled promotion gate: several symbols' out-of-sample reports judged as one, by the unchanged gate."""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

import pytest

from silver_bot.backtest.gate import GateInputError
from silver_bot.backtest.pooled_gate import FROZEN_SYMBOLS, main, pool

SYMBOLS = FROZEN_SYMBOLS["top_down_ob_v4"]
RANGES = {
    "training": ("2022-01-01T00:00:00+00:00", "2024-11-18T09:35:00+00:00"),
    "validation": ("2024-11-18T09:36:00+00:00", "2025-11-04T04:47:00+00:00"),
    "final_test": ("2025-11-04T04:48:00+00:00", "2026-10-20T23:59:00+00:00"),
}


def trade(day: int, r: float, *, exit_day: int | None = None, hour: int = 0) -> dict[str, Any]:
    """A trade entered on 2025-11-<day> that risks 50 (0.5% of 10,000)."""
    exit_day = day if exit_day is None else exit_day
    return {
        "entry_time": f"2025-11-{day:02d}T{hour:02d}:00:00+00:00",
        "exit_time": f"2025-11-{exit_day:02d}T{hour + 1:02d}:00:00+00:00",
        "realized_r": r,
        "realized_pnl": 50.0 * r,
        "fees": 1.0,
        "funding": 0.0,
        "session_name": "any_hour",
    }


def symbol_report(symbol: str, final: list, training: list) -> dict[str, Any]:
    trades = {"training": training, "validation": [], "final_test": final}
    return {
        "method": "chronological_split",
        "fractions": {"training": 0.6, "validation": 0.2, "final_test": 0.2},
        "parameters_tuned": False,
        "strategy": "top_down_ob_v4",
        "symbol": symbol,
        "segments": {
            name: {
                "candles": 100,
                "start": start,
                "end": end,
                "metrics": {"total_trades": len(trades[name])},
                "kill_switch": {"mode": "simulated_per_run_daily_reset", "trips": 1, "trip_log": []},
                "initial_balance": 10_000.0,
                "trades": trades[name],
            }
            for name, (start, end) in RANGES.items()
        },
    }


def reports(final: dict[str, list] | None = None, training: dict[str, list] | None = None) -> list[dict[str, Any]]:
    """One report per frozen symbol; symbols not named have no trades (training defaults to one +1R trade each)."""
    final = final or {}
    return [
        symbol_report(s, final.get(s, []), [trade(1, 1.0)] if training is None else training.get(s, []))
        for s in SYMBOLS
    ]


def final_metrics(**final: list) -> dict[str, Any]:
    return pool(reports(final))["segments"]["final_test"]["metrics"]


def t_stat(values: list[float]) -> float:
    return statistics.fmean(values) / (statistics.stdev(values) / math.sqrt(len(values)))


def test_pooled_final_test_is_one_union_of_trades() -> None:
    metrics = final_metrics(
        BTCUSDT=[trade(5, 2.0), trade(6, -1.0)], ETHUSDT=[trade(7, 2.0), trade(8, -1.0), trade(9, -1.0)]
    )

    assert metrics["total_trades"] == 5
    assert metrics["average_r"] == pytest.approx(0.2)
    assert metrics["profit_factor"] == pytest.approx(200 / 150)
    assert metrics["realized_rr"] == pytest.approx(2.0)


def test_same_day_r_is_summed_and_the_lower_t_stat_is_used() -> None:
    # Both symbols win and lose on the same days, so twice the trades carry no more evidence than one symbol.
    rs = [2.0, -1.0, 2.0, -1.0, 2.0]
    metrics = final_metrics(
        BTCUSDT=[trade(5 + i, r) for i, r in enumerate(rs)], ETHUSDT=[trade(5 + i, r, hour=3) for i, r in enumerate(rs)]
    )

    assert metrics["trade_r_t_stat"] == pytest.approx(t_stat(rs + rs))
    assert metrics["day_r_t_stat"] == pytest.approx(t_stat([2 * r for r in rs]))
    assert metrics["r_t_stat"] == metrics["day_r_t_stat"] < metrics["trade_r_t_stat"]


def test_trade_t_stat_is_used_when_the_day_t_stat_is_higher() -> None:
    # Same-day trades offset each other, so the day sums are steadier than the trades.
    metrics = final_metrics(
        BTCUSDT=[trade(5, 2.0), trade(6, 2.0), trade(7, -1.0), trade(8, 2.0)],
        ETHUSDT=[trade(5, -1.0, hour=3), trade(6, -1.0, hour=3), trade(7, 2.0, hour=3), trade(8, -1.5, hour=3)],
    )

    assert metrics["day_r_t_stat"] == pytest.approx(t_stat([1.0, 1.0, 1.0, 0.5]))
    assert metrics["r_t_stat"] == metrics["trade_r_t_stat"] < metrics["day_r_t_stat"]


def test_drawdown_runs_across_symbols_in_exit_order_on_one_account() -> None:
    # Exit order: ETH +100, ETH -100, BTC -100. From the 10,100 peak that is 200 down on one 10,000 account.
    # In entry order the deepest point would be only 100 down.
    pooled = pool(reports({"BTCUSDT": [trade(1, -2.0, exit_day=5)], "ETHUSDT": [trade(2, 2.0, exit_day=3), trade(4, -2.0)]}))

    assert pooled["segments"]["final_test"]["metrics"]["max_drawdown_percent"] == pytest.approx(200 / 10_000)
    assert pooled["segments"]["final_test"]["initial_balance"] == 10_000.0


def test_losses_spread_over_symbols_add_up_on_one_account() -> None:
    # One 2R loss on each of the 15 symbols: 1,500 on one 10,000 account, 15% down, past the gate's 10%.
    # Divided over 15 accounts' balances it would read 1%.
    metrics = final_metrics(**{s: [trade(1 + i, -2.0)] for i, s in enumerate(SYMBOLS)})

    assert metrics["max_drawdown_percent"] == pytest.approx(0.15)


def test_training_average_r_is_pooled() -> None:
    pooled = pool(reports(training={"BTCUSDT": [trade(1, 1.0)], "ETHUSDT": [trade(2, 3.0), trade(3, -1.0)]}))

    assert pooled["segments"]["training"]["metrics"]["average_r"] == pytest.approx(1.0)


def test_a_symbol_without_trades_pools_as_none() -> None:
    assert final_metrics(BTCUSDT=[trade(5, 2.0), trade(6, -1.0)])["total_trades"] == 2
    assert final_metrics() is None


def test_pooled_segment_keeps_the_shared_range_and_sums_candles_and_trips() -> None:
    segment = pool(reports())["segments"]["final_test"]

    assert (segment["start"], segment["end"]) == RANGES["final_test"]
    assert segment["candles"] == 100 * len(SYMBOLS)
    assert segment["kill_switch"]["trips"] == len(SYMBOLS)


def _set(*keys: str, value: Any):
    def spoil(report: dict[str, Any]) -> None:
        target = report
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = value

    return spoil


def _no_trade_list(report: dict[str, Any]) -> None:
    del report["segments"]["training"]["trades"]


@pytest.mark.parametrize(
    "spoil",
    [
        _set("strategy", value="top_down_ob_v3"),
        _set("symbol", value="BTCUSDT"),
        _set("symbol", value="MATICUSDT"),
        _set("symbol", value=None),
        _set("segments", "final_test", "end", value="2026-10-19T23:59:00+00:00"),
        _set("segments", "validation", "start", value="2024-12-01T00:00:00+00:00"),
        _set("segments", "final_test", "initial_balance", value=20_000.0),
        _set("parameters_tuned", value=True),
        _set("method", value="walk_forward"),
        _set("fractions", value={"training": 0.7, "validation": 0.1, "final_test": 0.2}),
        _no_trade_list,
    ],
    ids=[
        "other strategy", "repeated symbol", "symbol not in the frozen list", "no symbol", "other final range",
        "other split point", "other balance", "parameters tuned", "other method", "other fractions", "no trade list",
    ],
)
def test_reports_that_do_not_belong_together_are_refused(spoil, tmp_path: Path) -> None:
    pooled = reports()
    spoil(pooled[1])

    with pytest.raises(GateInputError):
        pool(pooled)
    assert main(_write(tmp_path, *pooled) + ["--output-dir", str(_pooled_dir(tmp_path))]) == 2
    assert not (tmp_path / "pooled" / "promotion_gate.json").exists()


def test_a_missing_symbol_is_refused() -> None:
    with pytest.raises(GateInputError, match="frozen"):
        pool(reports()[1:])


def test_a_run_without_the_carried_over_look_log_is_refused(tmp_path: Path) -> None:
    out = tmp_path / "pooled"

    assert main(_write(tmp_path, *reports()) + ["--output-dir", str(out)]) == 2
    assert not out.exists()


def test_a_look_log_without_this_data_range_is_refused(tmp_path: Path) -> None:
    out = tmp_path / "pooled"
    out.mkdir()
    other = {"data_start": "2020-01-01T00:00:00+00:00", "data_end": RANGES["final_test"][1], "passed": False}
    (out / "promotion_gate_log.jsonl").write_text(json.dumps(other) + "\n", encoding="utf-8")

    assert main(_write(tmp_path, *reports()) + ["--output-dir", str(out)]) == 2
    assert not (out / "promotion_gate.json").exists()


def test_output_never_overwrites_an_input_report(tmp_path: Path) -> None:
    args = _write(tmp_path, *reports())
    _pooled_dir(tmp_path, tmp_path / "BTCUSDT")

    assert main(args + ["--output-dir", str(tmp_path / "BTCUSDT")]) == 2


def _write(tmp_path: Path, *written: dict[str, Any]) -> list[str]:
    args = []
    for report in written:
        path = tmp_path / str(report.get("symbol")) / "out_of_sample_validation_report.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report), encoding="utf-8")
        args += ["--report", str(path)]
    return args


def _pooled_dir(tmp_path: Path, out: Path | None = None) -> Path:
    """An output directory holding the gate log of two earlier runs on this data range."""
    out = out or tmp_path / "pooled"
    out.mkdir(parents=True, exist_ok=True)
    past = {"data_start": RANGES["training"][0], "data_end": RANGES["final_test"][1], "passed": False}
    (out / "promotion_gate_log.jsonl").write_text(json.dumps(past) + "\n" + json.dumps(past) + "\n", encoding="utf-8")
    return out


def test_pooled_run_counts_the_carried_over_looks(tmp_path: Path) -> None:
    out = _pooled_dir(tmp_path)
    args = _write(tmp_path, *reports({"BTCUSDT": [trade(5, 2.0)], "ETHUSDT": [trade(6, -1.0)]}))

    assert main(args + ["--output-dir", str(out)]) == 1  # 2 trades fail the count

    verdict = json.loads((out / "promotion_gate.json").read_text(encoding="utf-8"))
    assert verdict["strategy"] == "top_down_ob_v4"
    assert verdict["t_stat_bar"] == 3.0
    assert len((out / "promotion_gate_log.jsonl").read_text(encoding="utf-8").splitlines()) == 3
    pooled = json.loads((out / "out_of_sample_validation_report.json").read_text(encoding="utf-8"))
    assert pooled["symbols"] == list(SYMBOLS)
    assert [Path(source["report"]).parent.name for source in pooled["sources"]] == list(SYMBOLS)
    assert all(len(source["sha256"]) == 64 for source in pooled["sources"])
