import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from silver_bot.backtest import BacktestConfig, BacktestEngine, build_backtest_config, run_backtest
from silver_bot.backtest.sim_kill_switch import SimulatedKillSwitch
from silver_bot.config import AppConfig, TradingMode
from silver_bot.models import Candle
from silver_bot.monitoring import StructuredAuditLogger
from silver_bot.risk import RiskManagementEngine
from silver_bot.strategy import SilverBulletSignal, SilverBulletStrategyEngine

# Deterministic synthetic series for the equivalence test. SYNTHETIC_SEED was chosen
# by scanning seeds until the 3-day series produced several trades, so the window is
# compared on real signals and not only on rejections.
SYNTHETIC_SEED = 1
SYNTHETIC_DAYS = 3
MONDAY_UTC = datetime(2026, 1, 5, 0, 0, tzinfo=UTC)


def synthetic_candles(
    seed: int = SYNTHETIC_SEED,
    *,
    days: int = SYNTHETIC_DAYS,
    start: datetime = MONDAY_UTC,
    volatility: float = 0.0012,
) -> list[Candle]:
    """Seeded 1m random walk with sticky trend regimes and occasional spikes."""

    rng = random.Random(seed)
    price = 30_000.0
    drift = 0.0
    result: list[Candle] = []
    for index in range(days * 24 * 60):
        if index % 45 == 0:
            drift = rng.choice((-1.0, 0.0, 1.0)) * volatility * 0.4
        move = drift + rng.gauss(0.0, volatility)
        if rng.random() < 0.03:
            move *= 4
        open_ = price
        close = max(1.0, open_ * (1 + move))
        high = max(open_, close) * (1 + abs(rng.gauss(0.0, volatility * 0.5)))
        low = min(open_, close) * (1 - abs(rng.gauss(0.0, volatility * 0.5)))
        opened = start + timedelta(minutes=index)
        result.append(
            Candle(
                symbol="BTCUSDT",
                timeframe="1m",
                open_time=opened,
                close_time=opened + timedelta(minutes=1),
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=1000.0,
            )
        )
        price = close
    return result


class RecordingStrategy(SilverBulletStrategyEngine):
    """Strategy engine that records every signal it returns, approved or not."""

    def __init__(self) -> None:
        super().__init__()
        self.signals: list[SilverBulletSignal] = []

    def evaluate(self, candles):
        signal = super().evaluate(candles)
        self.signals.append(signal)
        return signal


def run_with_window(candles: list[Candle], window: int | None):
    result, _ = run_recording(candles, window)
    return result


def run_recording(candles: list[Candle], window: int | None):
    config = BacktestConfig(strategy_window=window)
    strategy = RecordingStrategy()
    with SimulatedKillSwitch() as kill_switch:
        risk_engine = RiskManagementEngine(config.risk, kill_switch=kill_switch)
        result = BacktestEngine(strategy=strategy, config=config, risk_engine=risk_engine).run(candles)
    return result, strategy.signals


def test_window_matches_full_history_on_synthetic_days() -> None:
    candles = synthetic_candles()

    full, full_signals = run_recording(candles, None)
    windowed, windowed_signals = run_recording(candles, 200)

    assert len(full.trades) >= 3
    # Every signal the strategy returned (direction, time, entry, stop, target, reason,
    # score), including approved signals whose order never fills, must be identical.
    assert any(signal.entry_price is not None for signal in full_signals)
    assert windowed_signals == full_signals
    assert windowed.trades == full.trades
    assert windowed.rejected_signals == full.rejected_signals


def test_window_default_is_1440() -> None:
    assert BacktestConfig().strategy_window == 1440


def test_window_below_64_rejected() -> None:
    with pytest.raises(ValueError, match="strategy_window"):
        BacktestConfig(strategy_window=63)
    assert BacktestConfig(strategy_window=64).strategy_window == 64
    assert BacktestConfig(strategy_window=None).strategy_window is None


def test_audit_logger_can_skip_retention(tmp_path: Path) -> None:
    log_path = tmp_path / "audit.jsonl"
    logger = StructuredAuditLogger(log_path, retain_events=False)

    event = logger.log("bot_started", "Backtest started", context={"mode": "backtest"})

    assert logger.events == []
    assert event.event_type == "bot_started"
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event_type"] == "bot_started"


def test_audit_logger_retains_events_by_default() -> None:
    logger = StructuredAuditLogger()

    logger.log("bot_started", "Backtest started")

    assert len(logger.events) == 1


def test_runner_engines_do_not_retain_audit_events(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: list[StructuredAuditLogger] = []
    original_init = BacktestEngine.__init__

    def capturing_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        captured.append(self.audit)

    monkeypatch.setattr(BacktestEngine, "__init__", capturing_init)
    settings = AppConfig(mode=TradingMode.BACKTEST, paper_trading=False)

    run_backtest(settings, synthetic_candles(days=1), tmp_path / "reports", inputs={})

    assert captured
    for logger in captured:
        assert logger.events == []


def test_build_backtest_config_uses_default_window(tmp_path: Path) -> None:
    settings = AppConfig(mode=TradingMode.BACKTEST, paper_trading=False)

    config = build_backtest_config(settings, export_dir=None, kill_switch_path=tmp_path / "KILL_SWITCH")

    assert config.strategy_window == 1440
