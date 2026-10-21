import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import silver_bot
from silver_bot.backtest import build_backtest_config, run_backtest
from silver_bot.config import AppConfig, TradingMode
from silver_bot.models import Candle, SignalDirection
from silver_bot.readiness import evaluate_live_readiness
from silver_bot.strategy.models import SilverBulletSignal


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
