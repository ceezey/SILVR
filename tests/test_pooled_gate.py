"""Pooled promotion gate: several symbols' out-of-sample reports judged as one, by the unchanged gate."""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

import pytest

from silver_bot.backtest.gate import GateInputError
from silver_bot.backtest.pooled_gate import main, pool

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


def symbol_report(symbol: str, final: list, training: list | None = None, **overrides: Any) -> dict[str, Any]:
    trades = {"training": [trade(1, 1.0)] if training is None else training, "validation": [], "final_test": final}
    report = {
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
    report.update(overrides)
    return report


def final_metrics(*reports: dict[str, Any]) -> dict[str, Any]:
    return pool(list(reports))["segments"]["final_test"]["metrics"]


def t_stat(values: list[float]) -> float:
    return statistics.fmean(values) / (statistics.stdev(values) / math.sqrt(len(values)))


def test_pooled_final_test_is_one_union_of_trades() -> None:
    metrics = final_metrics(
        symbol_report("BTCUSDT", [trade(5, 2.0), trade(6, -1.0)]),
        symbol_report("ETHUSDT", [trade(7, 2.0), trade(8, -1.0), trade(9, -1.0)]),
    )

    assert metrics["total_trades"] == 5
    assert metrics["average_r"] == pytest.approx(0.2)
    assert metrics["profit_factor"] == pytest.approx(200 / 150)
    assert metrics["realized_rr"] == pytest.approx(2.0)


def test_same_day_r_is_summed_and_the_lower_t_stat_is_used() -> None:
    # Both symbols win and lose on the same days, so twice the trades carry no more evidence than one symbol.
    rs = [2.0, -1.0, 2.0, -1.0, 2.0]
    btc = symbol_report("BTCUSDT", [trade(5 + i, r) for i, r in enumerate(rs)])
    eth = symbol_report("ETHUSDT", [trade(5 + i, r, hour=3) for i, r in enumerate(rs)])

    metrics = final_metrics(btc, eth)

    assert metrics["trade_r_t_stat"] == pytest.approx(t_stat(rs + rs))
    assert metrics["day_r_t_stat"] == pytest.approx(t_stat([2 * r for r in rs]))
    assert metrics["r_t_stat"] == metrics["day_r_t_stat"] < metrics["trade_r_t_stat"]


def test_trade_t_stat_is_used_when_the_day_t_stat_is_higher() -> None:
    # Same-day trades offset each other, so the day sums are steadier than the trades.
    btc = symbol_report("BTCUSDT", [trade(5, 2.0), trade(6, 2.0), trade(7, -1.0), trade(8, 2.0)])
    eth = symbol_report("ETHUSDT", [trade(5, -1.0, hour=3), trade(6, -1.0, hour=3), trade(7, 2.0, hour=3), trade(8, -1.5, hour=3)])

    metrics = final_metrics(btc, eth)

    assert metrics["day_r_t_stat"] == pytest.approx(t_stat([1.0, 1.0, 1.0, 0.5]))
    assert metrics["r_t_stat"] == metrics["trade_r_t_stat"] < metrics["day_r_t_stat"]


def test_drawdown_runs_across_symbols_in_exit_order() -> None:
    # Exit order: ETH +100, ETH -100, BTC -100. From the 20,100 peak that is 200 down, on 20,000 of balances.
    # In entry order the deepest point would be only 100 down.
    btc = symbol_report("BTCUSDT", [trade(1, -2.0, exit_day=5)])
    eth = symbol_report("ETHUSDT", [trade(2, 2.0, exit_day=3), trade(4, -2.0)])

    metrics = final_metrics(btc, eth)

    assert metrics["max_drawdown_percent"] == pytest.approx(200 / 20_000)
    assert pool([btc, eth])["segments"]["final_test"]["initial_balance"] == 20_000.0


def test_training_average_r_is_pooled() -> None:
    btc = symbol_report("BTCUSDT", [], training=[trade(1, 1.0)])
    eth = symbol_report("ETHUSDT", [], training=[trade(2, 3.0), trade(3, -1.0)])

    assert pool([btc, eth])["segments"]["training"]["metrics"]["average_r"] == pytest.approx(1.0)


def test_a_symbol_without_trades_pools_as_none() -> None:
    btc = symbol_report("BTCUSDT", [trade(5, 2.0), trade(6, -1.0)])
    eth = symbol_report("ETHUSDT", [])

    assert final_metrics(btc, eth)["total_trades"] == 2
    assert pool([symbol_report("BTCUSDT", []), eth])["segments"]["final_test"]["metrics"] is None


def test_pooled_segment_keeps_the_shared_range_and_sums_candles_and_trips() -> None:
    segment = pool([symbol_report("BTCUSDT", []), symbol_report("ETHUSDT", [])])["segments"]["final_test"]

    assert (segment["start"], segment["end"]) == RANGES["final_test"]
    assert segment["candles"] == 200
    assert segment["kill_switch"]["trips"] == 2


def _other_range(report: dict[str, Any]) -> None:
    report["segments"]["final_test"]["end"] = "2026-10-19T23:59:00+00:00"


def _no_trade_list(report: dict[str, Any]) -> None:
    del report["segments"]["training"]["trades"]


@pytest.mark.parametrize(
    "spoil",
    [
        lambda report: report.update(strategy="top_down_ob_v3"),
        lambda report: report.update(symbol="BTCUSDT"),
        lambda report: report.pop("symbol"),
        _other_range,
        _no_trade_list,
    ],
    ids=["other strategy", "repeated symbol", "no symbol", "other range", "no trade list"],
)
def test_reports_that_do_not_belong_together_are_refused(spoil, tmp_path: Path) -> None:
    btc = symbol_report("BTCUSDT", [trade(5, 2.0)])
    eth = symbol_report("ETHUSDT", [trade(6, 2.0)])
    spoil(eth)

    with pytest.raises(GateInputError):
        pool([btc, eth])
    assert main(_write(tmp_path, btc, eth) + ["--output-dir", str(tmp_path / "pooled")]) == 2
    assert not (tmp_path / "pooled").exists()


def test_output_never_overwrites_an_input_report(tmp_path: Path) -> None:
    args = _write(tmp_path, symbol_report("BTCUSDT", []), symbol_report("ETHUSDT", []))

    assert main(args + ["--output-dir", str(tmp_path / "BTCUSDT")]) == 2


def _write(tmp_path: Path, *reports: dict[str, Any]) -> list[str]:
    args = []
    for report in reports:
        path = tmp_path / report.get("symbol", "nosymbol") / "out_of_sample_validation_report.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report), encoding="utf-8")
        args += ["--report", str(path)]
    return args


def test_pooled_run_counts_the_carried_over_looks(tmp_path: Path) -> None:
    out = tmp_path / "pooled"
    out.mkdir()
    past = {"data_start": RANGES["training"][0], "data_end": RANGES["final_test"][1], "passed": False}
    (out / "promotion_gate_log.jsonl").write_text(json.dumps(past) + "\n" + json.dumps(past) + "\n", encoding="utf-8")
    args = _write(tmp_path, symbol_report("BTCUSDT", [trade(5, 2.0)]), symbol_report("ETHUSDT", [trade(6, -1.0)]))

    assert main(args + ["--output-dir", str(out)]) == 1  # 2 trades fail the count

    verdict = json.loads((out / "promotion_gate.json").read_text(encoding="utf-8"))
    assert verdict["strategy"] == "top_down_ob_v4"
    assert verdict["t_stat_bar"] == 3.0
    assert len((out / "promotion_gate_log.jsonl").read_text(encoding="utf-8").splitlines()) == 3
    pooled = json.loads((out / "out_of_sample_validation_report.json").read_text(encoding="utf-8"))
    assert pooled["symbols"] == ["BTCUSDT", "ETHUSDT"]
    assert [Path(source["report"]).parent.name for source in pooled["sources"]] == ["BTCUSDT", "ETHUSDT"]
    assert all(len(source["sha256"]) == 64 for source in pooled["sources"])
