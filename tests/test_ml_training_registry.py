import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from silver_bot.ml import (
    FeatureEngineeringPipeline,
    MLDataset,
    MLSetupRow,
    ModelRegistry,
    train_baseline_models,
)
from silver_bot.models import SignalDirection


def dataset_with_rows(count: int = 10) -> MLDataset:
    feature_names = FeatureEngineeringPipeline().feature_names
    rows = []
    for index in range(count):
        features = {name: 0.0 for name in feature_names}
        features["direction_long"] = 1.0
        features["entry_price"] = 100.0 + index
        features["stop_distance"] = 5.0
        features["target_distance"] = 10.0 + index
        features["reward_to_risk"] = 2.0 + (index * 0.1)
        features["setup_quality_score"] = 70.0 + index
        features["atr"] = 2.0
        features["recent_range"] = 3.0 + index
        rows.append(
            MLSetupRow(
                signal_time=datetime(2026, 1, 1, 12, 0, tzinfo=UTC) + timedelta(minutes=index),
                symbol="BTCUSDT",
                timeframe="1m",
                direction=SignalDirection.LONG,
                session_name="new_york_am",
                features=features,
                label=index % 2,
                outcome_time=datetime(2026, 1, 1, 13, 0, tzinfo=UTC) + timedelta(minutes=index),
            )
        )
    return MLDataset(rows=tuple(rows), feature_names=feature_names)


def test_baseline_training_saves_logistic_model_artifacts(tmp_path: Path) -> None:
    results = train_baseline_models(dataset_with_rows(), model_dir=tmp_path)

    logistic = next(result for result in results if result.model_name == "logistic_regression")

    assert logistic.artifact_path.exists()
    assert logistic.feature_list_path.exists()
    assert logistic.metrics_path.exists()
    assert "accuracy" in logistic.validation_metrics
    feature_payload = json.loads(logistic.feature_list_path.read_text(encoding="utf-8"))
    metrics_payload = json.loads(logistic.metrics_path.read_text(encoding="utf-8"))
    assert feature_payload["features"] == list(dataset_with_rows().feature_names)
    assert metrics_payload["split"]["test_rows"] > 0
    assert "Final test split is held out" in metrics_payload["note"]


def test_model_registry_registers_loads_and_switches_active_model(tmp_path: Path) -> None:
    results = train_baseline_models(dataset_with_rows(), model_dir=tmp_path / "models")
    logistic = next(result for result in results if result.model_name == "logistic_regression")
    registry = ModelRegistry(tmp_path / "registry.json")

    first = registry.register_model(
        model_name=logistic.model_name,
        model_type="classification",
        artifact_path=logistic.artifact_path,
        feature_list_path=logistic.feature_list_path,
        metrics_path=logistic.metrics_path,
        features_used=dataset_with_rows().feature_names,
        active_status=True,
    )
    second = registry.register_model(
        model_name="candidate_model",
        model_type="classification",
        artifact_path=logistic.artifact_path,
        feature_list_path=logistic.feature_list_path,
        metrics_path=logistic.metrics_path,
        features_used=dataset_with_rows().feature_names,
        active_status=False,
    )

    assert registry.active_model() is not None
    assert registry.active_model().model_id == first.model_id
    loaded_model = registry.load_model_artifact(first.model_id)
    assert hasattr(loaded_model, "predict_proba")

    active = registry.set_active(second.model_id)

    assert active.model_id == second.model_id
    assert registry.active_model().model_id == second.model_id
    assert len(registry.list_models()) == 2
