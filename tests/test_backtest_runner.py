import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import silver_bot
from silver_bot.backtest import ExitReason, build_backtest_config, run_backtest
from silver_bot.backtest.top_down_engine import TopDownBacktestEngine
from silver_bot.config import AppConfig, TradingMode
from silver_bot.data.funding import FundingRate, FundingSchedule
from silver_bot.models import Candle, SignalDirection
from silver_bot.readiness import evaluate_live_readiness
from silver_bot.strategy.models import SilverBulletSignal
from silver_bot.strategy.top_down import EntryPlan, StepResult


NO_TRIPS = {"mode": "simulated_per_run_daily_reset", "trips": 0, "trip_log": []}


def candles(count: int = 50) -> list[Candle]:
    start = datetime(2026, 1, 2, 14, 0, tzinfo=UTC)
    result = []
    for index in range(count):
        opened = start + timedelta(minutes=index)
        base = 100 + (index % 7)
        result.append(
            Candle(
                symbol="BTCUSDT",
                timeframe="1m",
                open_time=opened,
                close_time=opened + timedelta(minutes=1),
                open=base,
                high=base + 2,
                low=base - 2,
                close=base + 1,
                volume=1000,
            )
        )
    return result


def backtest_settings(**overrides) -> AppConfig:
    values = dict(mode=TradingMode.BACKTEST, paper_trading=False)
    values.update(overrides)
    return AppConfig(**values)


def test_run_writes_all_reports(tmp_path: Path) -> None:
    summary = run_backtest(backtest_settings(), candles(), tmp_path / "reports", inputs={"files": ["x.csv"], "gaps": 0})

    assert summary.candles == 50
    assert set(summary.report_paths) == {
        "backtest_report",
        "trades",
        "equity_curve",
        "rejected_signals",
        "out_of_sample_validation_report",
        "backtest_run",
    }
    for path in summary.report_paths.values():
        assert path.exists()


def test_reports_pass_readiness_report_checks(tmp_path: Path) -> None:
    summary = run_backtest(backtest_settings(), candles(), tmp_path / "reports", inputs={})

    report = evaluate_live_readiness(
        project_root=tmp_path,
        environ={
            "BACKTEST_REPORT_PATH": str(summary.report_paths["backtest_report"]),
            "OOS_VALIDATION_REPORT_PATH": str(summary.report_paths["out_of_sample_validation_report"]),
        },
    )
    failed = {item.name for item in report.failed_checks}

    assert "backtest_report_exists" not in failed
    assert "out_of_sample_validation_report_exists" not in failed


def test_out_of_sample_report_structure(tmp_path: Path) -> None:
    summary = run_backtest(backtest_settings(), candles(), tmp_path / "reports", inputs={})

    oos = json.loads(summary.report_paths["out_of_sample_validation_report"].read_text(encoding="utf-8"))

    assert oos["method"] == "chronological_split"
    assert oos["parameters_tuned"] is False
    assert oos["fractions"] == {"training": 0.6, "validation": 0.2, "final_test": 0.2}
    assert [oos["segments"][name]["candles"] for name in ("training", "validation", "final_test")] == [30, 10, 10]
    assert oos["segments"]["training"]["end"] < oos["segments"]["validation"]["start"]
    assert oos["segments"]["validation"]["end"] < oos["segments"]["final_test"]["start"]
    assert isinstance(oos["segments"]["final_test"]["metrics"], dict)
    for name in ("training", "validation", "final_test"):
        assert oos["segments"][name]["kill_switch"] == NO_TRIPS


def test_run_record_lists_inputs_costs_and_kill_switch_mode(tmp_path: Path) -> None:
    summary = run_backtest(backtest_settings(), candles(), tmp_path / "reports", inputs={"files": ["a.csv"], "gaps": 2})

    run = json.loads(summary.report_paths["backtest_run"].read_text(encoding="utf-8"))

    assert run["inputs"] == {"files": ["a.csv"], "gaps": 2}
    assert run["candles"] == 50
    assert run["symbol"] == "BTCUSDT"
    assert run["timeframe"] == "1m"
    assert run["slippage_bps"] == 5.0
    assert run["spread_bps"] == 3.0
    assert run["risk_per_trade"] == 0.005
    assert run["ml_filter_enabled"] is False
    assert run["package_version"] == silver_bot.__version__
    assert run["first_open_time"] == "2026-01-02T14:00:00+00:00"
    assert run["kill_switch"] == NO_TRIPS


def test_backtest_never_uses_real_kill_switch(tmp_path: Path) -> None:
    real = tmp_path / "KILL_SWITCH"
    real.write_text('{"reason": "owner"}', encoding="utf-8")
    settings = backtest_settings(kill_switch_enabled=True, kill_switch_path=real)

    sim = tmp_path / "sim" / "KILL_SWITCH"
    assert build_backtest_config(settings, export_dir=None, kill_switch_path=sim).risk.kill_switch_path == sim
    summary = run_backtest(settings, candles(), tmp_path / "reports", inputs={})

    assert real.read_text(encoding="utf-8") == '{"reason": "owner"}'
    assert "Kill switch is active" not in summary.report_paths["rejected_signals"].read_text(encoding="utf-8")


def test_simulated_kill_switch_is_on_even_when_settings_disable_it(tmp_path: Path) -> None:
    sim = tmp_path / "sim" / "KILL_SWITCH"

    config = build_backtest_config(backtest_settings(kill_switch_enabled=False), export_dir=None, kill_switch_path=sim)

    assert config.risk.kill_switch_path == sim


def test_tripping_run_reports_trip_count_and_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class AlwaysLosingStrategy:
        def evaluate(self, history):
            last = history[-1]
            return SilverBulletSignal(
                direction=SignalDirection.LONG,
                symbol=last.symbol,
                timeframe=last.timeframe,
                generated_at=last.open_time,
                reason=None,
                explanation="scripted",
                entry_price=100.0,
                stop_loss=98.0,
                take_profit=104.0,
                risk_reward_ratio=2.0,
                session_name="scripted",
                setup_quality_score=90,
            )

    monkeypatch.setattr("silver_bot.backtest.engine.SilverBulletStrategyEngine", AlwaysLosingStrategy)
    start = datetime(2026, 1, 2, 14, 0, tzinfo=UTC)
    stopped_out = [
        Candle(
            symbol="BTCUSDT",
            timeframe="1m",
            open_time=start + timedelta(minutes=index),
            close_time=start + timedelta(minutes=index + 1),
            open=100,
            high=101,
            low=97,
            close=100,
            volume=1000,
        )
        for index in range(20)
    ]

    summary = run_backtest(backtest_settings(), stopped_out, tmp_path / "reports", inputs={})

    run = json.loads(summary.report_paths["backtest_run"].read_text(encoding="utf-8"))
    assert run["kill_switch"]["mode"] == "simulated_per_run_daily_reset"
    assert run["kill_switch"]["trips"] >= 1
    assert len(run["kill_switch"]["trip_log"]) == run["kill_switch"]["trips"]
    first = run["kill_switch"]["trip_log"][0]
    assert first["reason"] == "Max consecutive losses limit reached"
    assert first["tripped_at"].startswith("2026-01-02T")
    assert first["reset_at"] is None
    oos = json.loads(summary.report_paths["out_of_sample_validation_report"].read_text(encoding="utf-8"))
    assert oos["segments"]["training"]["kill_switch"]["trips"] >= 1


def test_settings_reach_backtest_config(tmp_path: Path) -> None:
    settings = backtest_settings(
        max_risk_per_trade=0.004,
        max_daily_loss=0.01,
        max_leverage=2.0,
        ml_filter_enabled=True,
        ml_registry_path=tmp_path / "registry.json",
        ml_min_probability=0.7,
        ml_reduce_risk_threshold=0.6,
    )

    config = build_backtest_config(settings, export_dir=tmp_path, kill_switch_path=tmp_path / "sim" / "KILL_SWITCH")

    assert (config.risk.risk_per_trade, config.risk.max_daily_loss, config.risk.max_leverage) == (0.004, 0.01, 2.0)
    assert config.ml_filter.enabled is True
    assert config.ml_filter.registry_path == tmp_path / "registry.json"
    assert (config.ml_filter.min_probability, config.ml_filter.reduce_risk_threshold) == (0.7, 0.6)
    assert config.export_dir == tmp_path
    assert (config.slippage_bps, config.spread_bps) == (5.0, 3.0)


def test_empty_candles_raise(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one candle"):
        run_backtest(backtest_settings(), [], tmp_path / "reports", inputs={})


START = datetime(2026, 1, 2, 14, 0, tzinfo=UTC)
FUNDING = FundingSchedule(
    FundingRate(datetime(2026, 1, 2, 8, 0, tzinfo=UTC) + timedelta(hours=8 * k), 0.0) for k in range(3)
)


def read_report(summary, name: str) -> dict:
    return json.loads(summary.report_paths[name].read_text(encoding="utf-8"))


def spy_on_engine_runs(monkeypatch: pytest.MonkeyPatch) -> list[tuple[list[Candle], list[Candle], object]]:
    """Record (candles, warmup, result) of every TopDownBacktestEngine.run, in call order: full, then segments."""
    runs = []
    original = TopDownBacktestEngine.run

    def spy(self, run_candles, *, warmup=()):
        result = original(self, run_candles, warmup=warmup)
        runs.append((list(run_candles), list(warmup), result))
        return result

    monkeypatch.setattr(TopDownBacktestEngine, "run", spy)
    return runs


def script_strategy(monkeypatch: pytest.MonkeyPatch, entry_minutes: set[int]) -> list:
    """Make the engine build a strategy that plans a long on the given minutes (offsets from START) when trading.

    Returns the strategies built, one per engine run, each with a `calls` log of (open_time, trading).
    """
    built = []

    class Scripted:
        def __init__(self) -> None:
            self.calls: list[tuple[datetime, bool]] = []
            built.append(self)

        def step(self, candle: Candle, *, trading: bool = True) -> StepResult:
            self.calls.append((candle.open_time, trading))
            minute = int((candle.open_time - START) / timedelta(minutes=1))
            if not trading or minute not in entry_minutes:
                return StepResult(None, None, ())
            close = candle.close
            plan = EntryPlan("long", candle.close_time, close, close - 5, close + 50, None, "scripted", None, "scripted")
            return StepResult(plan, None, ())

    monkeypatch.setattr("silver_bot.backtest.top_down_engine.TopDownOBStrategy", Scripted)
    return built


def test_default_strategy_is_silver_bullet_and_reports_name(tmp_path: Path) -> None:
    summary = run_backtest(backtest_settings(), candles(), tmp_path / "reports", inputs={})

    assert read_report(summary, "out_of_sample_validation_report")["strategy"] == "silver_bullet"
    run = read_report(summary, "backtest_run")
    assert run["strategy"] == "silver_bullet"
    assert run["funding_file"] is None


def test_top_down_requires_funding(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="funding"):
        run_backtest(backtest_settings(), candles(), tmp_path / "reports", inputs={}, strategy="top_down_ob")


def test_unknown_strategy_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="strategy"):
        run_backtest(backtest_settings(), candles(), tmp_path / "reports", inputs={}, strategy="nope")


def test_top_down_segments_get_warmup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs = spy_on_engine_runs(monkeypatch)
    data = candles()

    summary = run_backtest(
        backtest_settings(), data, tmp_path / "reports", inputs={"funding_file": "f.csv"},
        strategy="top_down_ob", funding=FUNDING,
    )

    assert len(runs) == 4  # full, training, validation, final_test
    (full, no_warmup, _), training, validation, final = runs
    assert (full, no_warmup) == (data, [])
    assert [(len(c), len(w)) for c, w, _ in (training, validation, final)] == [(30, 0), (10, 30), (10, 40)]
    assert final[1] == data[:40]
    assert final[0] == data[40:]
    assert validation[1] == data[:30]
    assert read_report(summary, "out_of_sample_validation_report")["strategy"] == "top_down_ob"
    run = read_report(summary, "backtest_run")
    assert (run["strategy"], run["funding_file"]) == ("top_down_ob", "f.csv")


def test_warmup_never_trades(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs = spy_on_engine_runs(monkeypatch)
    built = script_strategy(monkeypatch, set(range(50)))  # would plan on every candle if it were called with trading=True
    data = candles()

    run_backtest(backtest_settings(), data, tmp_path / "reports", inputs={}, strategy="top_down_ob", funding=FUNDING)

    assert len(built) == 4  # a fresh strategy per run
    for strategy, (run_candles, warmup, result) in zip(built[2:], runs[2:]):  # validation and final_test
        assert warmup
        # Warm-up candles were fed with trading=False; only the segment's own candles trade.
        assert strategy.calls == [(c.open_time, False) for c in warmup] + [(c.open_time, True) for c in run_candles]
        first_close = run_candles[0].close_time
        assert result.trades or result.rejected_signals  # the scripted strategy did act on the segment itself
        assert all(trade.entry_time >= first_close for trade in result.trades)
        assert all(record.timestamp >= first_close for record in result.rejected_signals)
        assert result.equity_curve[0].timestamp == first_close
        assert len(result.equity_curve) in (len(run_candles), len(run_candles) + 1)  # +1 for an END_OF_DATA close


def test_open_position_closed_at_segment_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs = spy_on_engine_runs(monkeypatch)
    script_strategy(monkeypatch, {28})  # entry at the close of candle 28, one candle before training ends
    data = candles()

    run_backtest(backtest_settings(), data, tmp_path / "reports", inputs={}, strategy="top_down_ob", funding=FUNDING)

    training = runs[1]
    assert training[0][-1] == data[29]
    (trade,) = training[2].trades
    assert trade.exit_reason == ExitReason.END_OF_DATA
    assert trade.exit_time == data[29].open_time
    assert [len(result.trades) for _, _, result in runs[2:]] == [0, 0]  # the plan is warm-up history there
    assert runs[0][2].trades[-1].exit_time == data[-1].open_time  # the full run holds it to the last candle
