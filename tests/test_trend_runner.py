"""Trend runner: segment bounds, streaming, skipped segments, report shape, success standard and the CLI."""

import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from silvr.backtest import gate, trend_runner
from silvr.backtest.models import EquityPoint
from silvr.backtest.trend_engine import TrendDataError, TrendRunResult
from silvr.backtest.trend_runner import find_candle_files, run_trend_backtest, segment_bounds, success_standard
from silvr.backtest.validation import BacktestValidationSuite
from silvr.data.csv_loader import load_binance_kline_csv
from silvr.data.funding import FundingRate, write_funding_csv
from silvr.strategy.trend import params, sizing
from silvr.strategy.trend.params import ExchangeLimits

MINUTE = timedelta(minutes=1)
START = datetime(2024, 3, 1, tzinfo=UTC)
DAYS = 10
SYMBOLS = ("AAA", "BBB")


@pytest.fixture
def tiny_universe(monkeypatch: pytest.MonkeyPatch) -> None:
    for module in (params, sizing):
        monkeypatch.setattr(module, "SYMBOLS", SYMBOLS)
        monkeypatch.setattr(module, "LOOKBACKS", (2,))
    monkeypatch.setattr(sizing, "EXCHANGE_LIMITS", {s: ExchangeLimits(5.0, 0.001, 0.001) for s in SYMBOLS})


def write_month(path: Path, start: datetime, minutes: int, price: float = 100.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(minutes):
        t = start + i * MINUTE
        ms = int(t.timestamp() * 1000)
        rows.append(f"{ms},{price},{price},{price},{price},1.0,{ms + 59_999},0,0,0,0,0")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_data(tmp_path: Path) -> tuple[Path, Path]:
    candles, funding = tmp_path / "candles", tmp_path / "funding"
    funding.mkdir()
    rates = [FundingRate(START - timedelta(days=1) + k * timedelta(hours=8), 0.0) for k in range(3 * (DAYS + 3))]
    for symbol in SYMBOLS:
        write_month(candles / symbol / f"{symbol}-1m-2024-03.csv", START, DAYS * 1440)
        write_funding_csv(funding / f"{symbol}-funding.csv", rates)
    return candles, funding


def test_segment_bounds_real_data_range() -> None:
    first, last = datetime(2022, 1, 1, tzinfo=UTC), datetime(2026, 10, 20, 23, 59, tzinfo=UTC)
    bounds = segment_bounds(first, last)
    assert bounds["training"][0].isoformat() == "2022-01-01T00:00:00+00:00"
    assert bounds["final_test"][1].isoformat() == "2026-10-20T23:59:00+00:00"
    assert bounds["validation"][0] == bounds["training"][1] + MINUTE
    assert bounds["final_test"][0] == bounds["validation"][1] + MINUTE


def test_trend_report_data_range_matches_log(tiny_universe: None, tmp_path: Path) -> None:
    candles, funding = write_data(tmp_path)
    path = run_trend_backtest(
        candles_root=candles, funding_root=funding, output_dir=tmp_path / "out", segments=("training", "validation", "final_test"), k=1.0
    )
    segments = json.loads(path.read_text(encoding="utf-8"))["segments"]
    assert segments["training"]["start"] == START.isoformat()
    assert segments["final_test"]["end"] == (START + DAYS * 1440 * MINUTE - MINUTE).isoformat()


def test_segment_bounds_match_chronological_split_on_real_btc() -> None:
    root = Path(__file__).resolve().parents[1] / "data" / "candles"
    paths = sorted(root.glob("BTCUSDT-1m-*.csv"))
    if not paths:
        pytest.skip("data/candles is absent")
    loaded = load_binance_kline_csv(paths, symbol="BTCUSDT", timeframe="1m").candles
    split = BacktestValidationSuite().chronological_split(loaded, training_fraction=0.6, validation_fraction=0.2)
    bounds = segment_bounds(loaded[0].open_time, loaded[-1].open_time)
    for name, part in (("training", split.training), ("validation", split.validation), ("final_test", split.final_test)):
        assert bounds[name] == (part[0].open_time, part[-1].open_time)


def test_find_candle_files_sorted_and_error_when_none(tmp_path: Path) -> None:
    write_month(tmp_path / "AAA" / "AAA-1m-2024-04.csv", START, 1)
    write_month(tmp_path / "AAA" / "AAA-1m-2024-03.csv", START, 1)
    write_month(tmp_path / "BBB" / "BBB-1m-2024-03.csv", START, 1)
    assert [p.name for p in find_candle_files(tmp_path, "AAA")] == ["AAA-1m-2024-03.csv", "AAA-1m-2024-04.csv"]
    with pytest.raises(FileNotFoundError):
        find_candle_files(tmp_path, "CCC")


def test_skipped_segments_not_simulated(tiny_universe: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    candles, funding = write_data(tmp_path)
    built: list[object] = []

    class FakeEngine:
        def __init__(self, config, *, funding, history, k) -> None:
            built.append(history)

        def run(self, minutes) -> TrendRunResult:
            count = sum(1 for _ in minutes)
            assert count == 6 * 1440
            return TrendRunResult([], [], {"total_trades": 0}, None, Counter())

    monkeypatch.setattr(trend_runner, "TrendPortfolioEngine", FakeEngine)
    path = run_trend_backtest(
        candles_root=candles, funding_root=funding, output_dir=tmp_path / "out", segments=("training",), k=1.0
    )
    report = json.loads(path.read_text(encoding="utf-8"))
    assert len(built) == 1
    assert report["segments"]["validation"] == {"skipped": True}
    assert report["segments"]["final_test"] == {"skipped": True}
    assert report["segments"]["training"]["candles"] == 6 * 1440 * len(SYMBOLS)


def test_later_segment_gets_warmup_history_ending_the_day_before(
    tiny_universe: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candles, funding = write_data(tmp_path)
    seen: list[dict] = []

    class FakeEngine:
        def __init__(self, config, *, funding, history, k) -> None:
            seen.append(dict(history))

        def run(self, minutes) -> TrendRunResult:
            first = next(iter(minutes))
            assert all(c.open_time == START + 6 * 1440 * MINUTE for c in first.values())
            assert first["AAA"] is not first.get("BBB")
            return TrendRunResult([], [], {"total_trades": 0}, None, Counter())

    monkeypatch.setattr(trend_runner, "TrendPortfolioEngine", FakeEngine)
    run_trend_backtest(
        candles_root=candles, funding_root=funding, output_dir=tmp_path / "out", segments=("validation",), k=1.0
    )
    [history] = seen
    for symbol in SYMBOLS:
        days = [bar.day for bar in history[symbol]]
        assert len(days) == 6 and days[-1] == (START + timedelta(days=5)).date()


def test_minutes_are_fresh_dicts(tiny_universe: None, tmp_path: Path) -> None:
    candles, _ = write_data(tmp_path)
    files = {s: trend_runner._month_files(candles, s) for s in SYMBOLS}
    stream = trend_runner._minutes(files, START, START + 3 * MINUTE)
    maps = list(stream)
    assert len(maps) == 4 and len({id(m) for m in maps}) == 4


def test_report_shape_reads_in_gate(tiny_universe: None, tmp_path: Path) -> None:
    candles, funding = write_data(tmp_path)
    path = run_trend_backtest(
        candles_root=candles, funding_root=funding, output_dir=tmp_path / "out", segments=("training", "validation", "final_test"), k=1.0
    )
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["strategy"] == "trend_ensemble" and report["parameters_tuned"] is False
    assert report["symbols"] == list(SYMBOLS) and report["k"] == 1.0
    final = report["segments"]["final_test"]
    assert set(final) == {"candles", "start", "end", "metrics", "kill_switch", "success_standard", "rejections"}
    assert final["kill_switch"] == {"trips": 0, "tripped_at": None}
    assert final["candles"] == 2 * 1440 * len(SYMBOLS)
    verdict = gate.evaluate_gate(report)
    assert verdict.strategy == "trend_ensemble"


def test_missing_month_for_one_symbol_fails_closed(tiny_universe: None, tmp_path: Path) -> None:
    candles, funding = write_data(tmp_path)
    write_month(candles / "AAA" / "AAA-1m-2024-04.csv", datetime(2024, 4, 1, tzinfo=UTC), 10)
    with pytest.raises(TrendDataError, match=r"BBB.*2024-04"):
        run_trend_backtest(
            candles_root=candles, funding_root=funding, output_dir=tmp_path / "out", segments=("training",), k=1.0
        )


def test_misaligned_minutes_fail_closed(tiny_universe: None, tmp_path: Path) -> None:
    candles, funding = write_data(tmp_path)
    write_month(candles / "BBB" / "BBB-1m-2024-03.csv", START + MINUTE, DAYS * 1440 - 1)
    with pytest.raises(TrendDataError, match=r"BBB.*2024-03"):
        run_trend_backtest(
            candles_root=candles, funding_root=funding, output_dir=tmp_path / "out", segments=("training",), k=1.0
        )


def test_funding_gap_fails_closed_naming_symbol(tiny_universe: None, tmp_path: Path) -> None:
    candles, funding = write_data(tmp_path)
    write_funding_csv(funding / "BBB-funding.csv", [FundingRate(START - timedelta(days=1), 0.0)])
    with pytest.raises(TrendDataError, match="BBB"):
        run_trend_backtest(
            candles_root=candles, funding_root=funding, output_dir=tmp_path / "out", segments=("training",), k=1.0
        )


def week_points(*nets: float) -> list[EquityPoint]:
    """One daily point per week-ending Sunday, equity moving by `nets` from 15,000."""
    monday = datetime(2024, 3, 4, tzinfo=UTC)
    points, equity = [], 15_000.0
    for i, net in enumerate(nets):
        equity += net
        stamp = monday + timedelta(weeks=i, days=6, hours=23, minutes=59)
        points.append(EquityPoint(stamp, equity, 0.0, 0.0))
    return points


def test_success_standard() -> None:
    result = success_standard(week_points(100.0, -40.0), 15_000.0)
    assert result == {
        "weeks": 2,
        "average_weekly_net": 30.0,
        "losing_week_share": 0.5,
        "worst_week": -40.0,
        "target_weekly_net": 50.0,
        "met": False,
    }


def test_success_standard_met_and_empty() -> None:
    assert success_standard(week_points(60.0, 40.0, 60.0), 15_000.0)["met"] is True
    empty = success_standard([], 15_000.0)
    assert empty["weeks"] == 0 and empty["met"] is False


def test_cli_refuses_without_k(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(params, "SCALE_K", None)
    code = trend_runner.main(["--candles-root", str(tmp_path), "--funding-root", str(tmp_path), "--output-dir", str(tmp_path / "o")])
    assert code == 2
    assert "SCALE_K is not frozen" in capsys.readouterr().err
    assert not (tmp_path / "o").exists()


def test_cli_runs_training_with_k(tiny_universe: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    candles, funding = write_data(tmp_path)
    monkeypatch.setattr(params, "SCALE_K", 1.0)
    code = trend_runner.main(
        ["--candles-root", str(candles), "--funding-root", str(funding), "--output-dir", str(tmp_path / "o"), "--segments", "training"]
    )
    assert code == 0
    report = json.loads((tmp_path / "o" / "out_of_sample_validation_report.json").read_text(encoding="utf-8"))
    assert report["segments"]["final_test"] == {"skipped": True}
