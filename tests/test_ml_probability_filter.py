import json
import pickle
from datetime import UTC, datetime, timedelta
from pathlib import Path

from silver_bot.backtest import BacktestConfig, BacktestEngine
from silver_bot.ml import (
    FeatureEngineeringPipeline,
    MLDecision,
    MLFilterConfig,
    MLProbabilityFilter,
    ModelRegistry,
)
from silver_bot.models import Candle
from silver_bot.storage import SQLiteStorage
from silver_bot.strategy import SilverBulletStrategyConfig, SilverBulletStrategyEngine


class ConstantProbabilityModel:
    def __init__(self, probability: float) -> None:
        self.probability = probability

    def predict_proba(self, rows: list[list[float]]) -> list[float]:
        return [self.probability for _ in rows]


def candle(index: int, open_: float, high: float, low: float, close: float) -> Candle:
    opened = datetime(2026, 1, 2, 15, 0, tzinfo=UTC) + timedelta(minutes=index)
    return Candle(
        symbol="BTCUSDT",
        timeframe="1m",
        open_time=opened,
        close_time=opened + timedelta(minutes=1),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1000,
    )


def valid_long_setup() -> list[Candle]:
    return [
        candle(0, 110, 115, 109, 112),
        candle(1, 112, 118, 111, 116),
        candle(2, 116, 140, 114, 119),
        candle(3, 119, 120, 105, 107),
        candle(4, 107, 108, 99, 101),
        candle(5, 101, 102, 98, 100),
        candle(6, 100, 115, 99.5, 113),
        candle(7, 113, 145, 110, 142),
        candle(8, 112, 115, 105, 112),
    ]


def strategy() -> SilverBulletStrategyEngine:
    return SilverBulletStrategyEngine(
        SilverBulletStrategyConfig(
            swing_lookback=2,
            atr_period=3,
            minimum_rr=2.0,
            minimum_signal_score=70,
        )
    )


def active_filter(tmp_path: Path, probability: float) -> MLProbabilityFilter:
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    artifact_path = model_dir / "constant.pkl"
    feature_path = model_dir / "features.json"
    metrics_path = model_dir / "metrics.json"

    with artifact_path.open("wb") as handle:
        pickle.dump(ConstantProbabilityModel(probability), handle)
    feature_path.write_text(
        json.dumps({"features": list(FeatureEngineeringPipeline().feature_names)}),
        encoding="utf-8",
    )
    metrics_path.write_text(json.dumps({"validation_metrics": {"accuracy": 1.0}}), encoding="utf-8")

    registry = ModelRegistry(tmp_path / "registry.json")
    registry.register_model(
        model_name="constant",
        model_type="classification",
        artifact_path=artifact_path,
        feature_list_path=feature_path,
        metrics_path=metrics_path,
        features_used=FeatureEngineeringPipeline().feature_names,
        active_status=True,
    )
    return MLProbabilityFilter(
        MLFilterConfig(
            enabled=True,
            registry_path=tmp_path / "registry.json",
            min_probability=0.60,
            reduce_risk_threshold=0.55,
        )
    )


def test_ml_filter_approves_signal_above_min_probability(tmp_path: Path) -> None:
    candles = valid_long_setup()
    signal = strategy().evaluate(candles)

    result = active_filter(tmp_path, 0.72).evaluate(signal=signal, candles_at_signal=candles)

    assert result.decision == MLDecision.APPROVE
    assert result.probability == 0.72
    assert result.risk_multiplier == 1.0
    assert result.model_id is not None


def test_ml_filter_rejects_signal_below_reduce_risk_threshold(tmp_path: Path) -> None:
    candles = valid_long_setup()
    signal = strategy().evaluate(candles)

    result = active_filter(tmp_path, 0.40).evaluate(signal=signal, candles_at_signal=candles)

    assert result.decision == MLDecision.REJECT
    assert result.risk_multiplier == 0.0
    assert "below probability threshold" in result.reason


def test_ml_filter_reduces_risk_between_thresholds(tmp_path: Path) -> None:
    candles = valid_long_setup()
    signal = strategy().evaluate(candles)

    result = active_filter(tmp_path, 0.57).evaluate(signal=signal, candles_at_signal=candles)

    assert result.decision == MLDecision.REDUCE_RISK
    assert result.risk_multiplier == 0.5


def test_ml_filter_missing_model_falls_back_to_rule_based_signal(tmp_path: Path) -> None:
    candles = valid_long_setup()
    signal = strategy().evaluate(candles)
    ml_filter = MLProbabilityFilter(
        MLFilterConfig(enabled=True, registry_path=tmp_path / "missing-registry.json")
    )

    result = ml_filter.evaluate(signal=signal, candles_at_signal=candles)

    assert result.decision == MLDecision.APPROVE
    assert result.probability is None
    assert "No active ML model" in result.reason


def test_ml_filter_disabled_leaves_signal_unchanged() -> None:
    candles = valid_long_setup()
    signal = strategy().evaluate(candles)

    result = MLProbabilityFilter(MLFilterConfig(enabled=False)).evaluate(
        signal=signal,
        candles_at_signal=candles,
    )

    assert result.decision == MLDecision.APPROVE
    assert result.probability is None
    assert result.risk_multiplier == 1.0
    assert "disabled" in result.reason


def test_ml_prediction_is_stored_in_database(tmp_path: Path) -> None:
    candles = valid_long_setup()
    signal = strategy().evaluate(candles)
    result = active_filter(tmp_path, 0.72).evaluate(signal=signal, candles_at_signal=candles)
    storage = SQLiteStorage(tmp_path / "silver_bot.sqlite3")

    storage.initialize()
    storage.save_ml_prediction(result)

    assert storage.count_rows("ml_predictions") == 1


def test_backtest_includes_ml_probability_and_reduces_risk(tmp_path: Path) -> None:
    candles = [
        *valid_long_setup(),
        candle(9, 112, 141, 105, 140),
    ]
    result = BacktestEngine(
        strategy=strategy(),
        config=BacktestConfig(maker_fee=0.0, taker_fee=0.0),
        ml_filter=active_filter(tmp_path, 0.57),
    ).run(candles)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.ml_probability == 0.57
    assert trade.ml_decision == MLDecision.REDUCE_RISK.value
    assert trade.position_size == 3.125
