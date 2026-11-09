"""Baseline ML model training for setup outcome classification."""

from __future__ import annotations

import json
import math
import pickle
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from silvr.ml.dataset import MLDataset, time_based_split


@dataclass(frozen=True, slots=True)
class BaselineTrainingResult:
    """Saved baseline model and validation metadata."""

    model_name: str
    artifact_path: Path
    feature_list_path: Path
    metrics_path: Path
    validation_metrics: dict[str, float]


@dataclass(slots=True)
class SimpleLogisticRegressionModel:
    """Small dependency-free logistic regression baseline."""

    feature_names: tuple[str, ...]
    weights: list[float]
    bias: float
    means: list[float]
    scales: list[float]

    @classmethod
    def fit(
        cls,
        x_train: list[list[float]],
        y_train: list[int],
        feature_names: tuple[str, ...],
        *,
        learning_rate: float = 0.1,
        iterations: int = 500,
    ) -> "SimpleLogisticRegressionModel":
        """Fit a logistic classifier using deterministic gradient descent."""

        if not x_train or not y_train:
            raise ValueError("Training data cannot be empty")
        width = len(feature_names)
        means, scales = _normalization_stats(x_train, width)
        normalized = [_normalize(row, means, scales) for row in x_train]
        weights = [0.0] * width
        bias = _initial_bias(y_train)

        for _ in range(iterations):
            gradients = [0.0] * width
            bias_gradient = 0.0
            for row, label in zip(normalized, y_train, strict=True):
                probability = _sigmoid(_dot(weights, row) + bias)
                error = probability - label
                for index, value in enumerate(row):
                    gradients[index] += error * value
                bias_gradient += error
            scale = 1.0 / len(y_train)
            for index in range(width):
                weights[index] -= learning_rate * gradients[index] * scale
            bias -= learning_rate * bias_gradient * scale

        return cls(
            feature_names=feature_names,
            weights=weights,
            bias=bias,
            means=means,
            scales=scales,
        )

    def predict_proba(self, rows: list[list[float]]) -> list[float]:
        """Return positive-class probabilities."""

        probabilities: list[float] = []
        for row in rows:
            normalized = _normalize(row, self.means, self.scales)
            probabilities.append(_sigmoid(_dot(self.weights, normalized) + self.bias))
        return probabilities


def train_baseline_models(
    dataset: MLDataset,
    *,
    model_dir: Path,
    train_fraction: float = 0.6,
    validation_fraction: float = 0.2,
) -> list[BaselineTrainingResult]:
    """Train baseline setup classifiers and save artifacts.

    The final test split is created but intentionally not scored here, so it
    remains untouched for later out-of-sample validation.
    """

    split = time_based_split(
        dataset,
        train_fraction=train_fraction,
        validation_fraction=validation_fraction,
    )
    if not split.train:
        raise ValueError("Training split is empty")
    if not split.validation:
        raise ValueError("Validation split is empty")

    model_dir.mkdir(parents=True, exist_ok=True)
    feature_list_path = model_dir / "feature_list.json"
    feature_list_path.write_text(
        json.dumps({"features": list(dataset.feature_names)}, indent=2),
        encoding="utf-8",
    )

    x_train, y_train = dataset.as_matrices(split.train)
    x_validation, y_validation = dataset.as_matrices(split.validation)
    split_metadata = {
        "train_rows": len(split.train),
        "validation_rows": len(split.validation),
        "test_rows": len(split.test),
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }

    results: list[BaselineTrainingResult] = []
    logistic = SimpleLogisticRegressionModel.fit(x_train, y_train, dataset.feature_names)
    results.append(
        _save_model_result(
            model_dir=model_dir,
            model_name="logistic_regression",
            model=logistic,
            feature_list_path=feature_list_path,
            probabilities=logistic.predict_proba(x_validation),
            y_validation=y_validation,
            split_metadata=split_metadata,
        )
    )

    results.extend(
        _train_optional_sklearn_models(
            model_dir=model_dir,
            feature_list_path=feature_list_path,
            feature_names=dataset.feature_names,
            x_train=x_train,
            y_train=y_train,
            x_validation=x_validation,
            y_validation=y_validation,
            split_metadata=split_metadata,
        )
    )
    return results


def _train_optional_sklearn_models(
    *,
    model_dir: Path,
    feature_list_path: Path,
    feature_names: tuple[str, ...],
    x_train: list[list[float]],
    y_train: list[int],
    x_validation: list[list[float]],
    y_validation: list[int],
    split_metadata: dict[str, Any],
) -> list[BaselineTrainingResult]:
    if len(set(y_train)) < 2:
        return []
    try:
        from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    except ImportError:
        return []

    results: list[BaselineTrainingResult] = []
    for model_name, estimator in (
        (
            "random_forest",
            RandomForestClassifier(n_estimators=50, random_state=0),
        ),
        (
            "gradient_boosting",
            GradientBoostingClassifier(random_state=0),
        ),
    ):
        estimator.fit(x_train, y_train)
        probabilities = [float(value[1]) for value in estimator.predict_proba(x_validation)]
        results.append(
            _save_model_result(
                model_dir=model_dir,
                model_name=model_name,
                model={"estimator": estimator, "feature_names": feature_names},
                feature_list_path=feature_list_path,
                probabilities=probabilities,
                y_validation=y_validation,
                split_metadata=split_metadata,
            )
        )
    return results


def _save_model_result(
    *,
    model_dir: Path,
    model_name: str,
    model: Any,
    feature_list_path: Path,
    probabilities: list[float],
    y_validation: list[int],
    split_metadata: dict[str, Any],
) -> BaselineTrainingResult:
    artifact_path = model_dir / f"{model_name}.pkl"
    with artifact_path.open("wb") as handle:
        pickle.dump(model, handle)

    validation_metrics = _classification_metrics(y_validation, probabilities)
    metrics_path = model_dir / f"{model_name}_validation_metrics.json"
    metrics_payload = {
        "model_name": model_name,
        "split": split_metadata,
        "validation_metrics": validation_metrics,
        "note": "Final test split is held out and not optimized on.",
    }
    metrics_path.write_text(json.dumps(metrics_payload, indent=2), encoding="utf-8")
    return BaselineTrainingResult(
        model_name=model_name,
        artifact_path=artifact_path,
        feature_list_path=feature_list_path,
        metrics_path=metrics_path,
        validation_metrics=validation_metrics,
    )


def _classification_metrics(labels: list[int], probabilities: list[float]) -> dict[str, float]:
    predictions = [1 if probability >= 0.5 else 0 for probability in probabilities]
    true_positive = sum(1 for prediction, label in zip(predictions, labels, strict=True) if prediction == 1 and label == 1)
    true_negative = sum(1 for prediction, label in zip(predictions, labels, strict=True) if prediction == 0 and label == 0)
    false_positive = sum(1 for prediction, label in zip(predictions, labels, strict=True) if prediction == 1 and label == 0)
    false_negative = sum(1 for prediction, label in zip(predictions, labels, strict=True) if prediction == 0 and label == 1)
    total = len(labels)
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "sample_count": float(total),
        "accuracy": (true_positive + true_negative) / total if total else 0.0,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "positive_rate": sum(labels) / total if total else 0.0,
        "roc_auc": _roc_auc(labels, probabilities),
    }


def _roc_auc(labels: list[int], probabilities: list[float]) -> float:
    positives = [score for score, label in zip(probabilities, labels, strict=True) if label == 1]
    negatives = [score for score, label in zip(probabilities, labels, strict=True) if label == 0]
    if not positives or not negatives:
        return 0.0
    wins = 0.0
    comparisons = 0
    for positive in positives:
        for negative in negatives:
            comparisons += 1
            if positive > negative:
                wins += 1.0
            elif positive == negative:
                wins += 0.5
    return wins / comparisons if comparisons else 0.0


def _normalization_stats(rows: list[list[float]], width: int) -> tuple[list[float], list[float]]:
    means: list[float] = []
    scales: list[float] = []
    for index in range(width):
        values = [row[index] for row in rows]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        scale = math.sqrt(variance) or 1.0
        means.append(mean)
        scales.append(scale)
    return means, scales


def _normalize(row: list[float], means: list[float], scales: list[float]) -> list[float]:
    return [(value - means[index]) / scales[index] for index, value in enumerate(row)]


def _initial_bias(labels: list[int]) -> float:
    positive_rate = min(0.99, max(0.01, sum(labels) / len(labels)))
    return math.log(positive_rate / (1.0 - positive_rate))


def _dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)
