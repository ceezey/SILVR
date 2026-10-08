"""ML probability filter for existing rule-based setup signals."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from silver_bot.ml.features import FeatureEngineeringPipeline
from silver_bot.ml.registry import ModelRegistry, ModelRegistryEntry
from silver_bot.models import Candle, SignalDirection
from silver_bot.strategy import SilverBulletSignal


class MLDecision(str, Enum):
    """Allowed ML filter decisions."""

    APPROVE = "approve"
    REJECT = "reject"
    REDUCE_RISK = "reduce_risk"


@dataclass(frozen=True, slots=True)
class MLFilterConfig:
    """Configuration for optional ML filtering."""

    enabled: bool = False
    registry_path: Path = Path("models/model_registry.json")
    min_probability: float = 0.60
    reduce_risk_threshold: float = 0.55
    reduced_risk_multiplier: float = 0.5

    def __post_init__(self) -> None:
        if not 0 <= self.reduce_risk_threshold <= 1:
            raise ValueError("reduce_risk_threshold must be between 0 and 1")
        if not 0 <= self.min_probability <= 1:
            raise ValueError("min_probability must be between 0 and 1")
        if self.reduce_risk_threshold > self.min_probability:
            raise ValueError("reduce_risk_threshold must be less than or equal to min_probability")
        if not 0 < self.reduced_risk_multiplier <= 1:
            raise ValueError("reduced_risk_multiplier must be greater than 0 and no more than 1")


@dataclass(frozen=True, slots=True)
class MLFilterResult:
    """ML probability decision for a rule-based signal."""

    signal_id: str
    decision: MLDecision
    probability: float | None
    threshold: float
    reduce_risk_threshold: float
    risk_multiplier: float
    model_id: str | None
    model_name: str | None
    reason: str
    features_snapshot: dict[str, float] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MLProbabilityFilter:
    """Approve, reject, or downsize existing rule-based signals."""

    def __init__(
        self,
        config: MLFilterConfig | None = None,
        *,
        feature_pipeline: FeatureEngineeringPipeline | None = None,
        registry: ModelRegistry | None = None,
    ) -> None:
        self.config = config or MLFilterConfig()
        self.feature_pipeline = feature_pipeline or FeatureEngineeringPipeline()
        self.registry = registry or ModelRegistry(self.config.registry_path)

    def evaluate(
        self,
        *,
        signal: SilverBulletSignal,
        candles_at_signal: list[Candle] | tuple[Candle, ...],
    ) -> MLFilterResult:
        """Evaluate a deterministic setup signal with the active ML model."""

        signal_id = build_signal_id(signal)
        if not self.config.enabled:
            return MLFilterResult(
                signal_id=signal_id,
                decision=MLDecision.APPROVE,
                probability=None,
                threshold=self.config.min_probability,
                reduce_risk_threshold=self.config.reduce_risk_threshold,
                risk_multiplier=1.0,
                model_id=None,
                model_name=None,
                reason="ML filter disabled; rule-based signal unchanged",
            )
        if signal.direction == SignalDirection.NO_TRADE:
            return MLFilterResult(
                signal_id=signal_id,
                decision=MLDecision.APPROVE,
                probability=None,
                threshold=self.config.min_probability,
                reduce_risk_threshold=self.config.reduce_risk_threshold,
                risk_multiplier=1.0,
                model_id=None,
                model_name=None,
                reason="ML filter only processes existing rule-based trade signals",
            )

        active_entry = self._active_entry()
        if active_entry is None:
            return MLFilterResult(
                signal_id=signal_id,
                decision=MLDecision.APPROVE,
                probability=None,
                threshold=self.config.min_probability,
                reduce_risk_threshold=self.config.reduce_risk_threshold,
                risk_multiplier=1.0,
                model_id=None,
                model_name=None,
                reason="No active ML model found; rule-based signal unchanged",
            )

        features = self.feature_pipeline.build_features(
            signal=signal,
            candles_at_signal=candles_at_signal,
        )
        model = self.registry.load_model_artifact(active_entry.model_id)
        feature_order = active_entry.features_used or tuple(features)
        row = [[float(features.get(name, 0.0)) for name in feature_order]]
        probability = self._predict_probability(model, row)

        if probability >= self.config.min_probability:
            decision = MLDecision.APPROVE
            risk_multiplier = 1.0
            reason = "ML approved setup"
        elif probability >= self.config.reduce_risk_threshold:
            decision = MLDecision.REDUCE_RISK
            risk_multiplier = self.config.reduced_risk_multiplier
            reason = "ML reduced risk for lower-confidence setup"
        else:
            decision = MLDecision.REJECT
            risk_multiplier = 0.0
            reason = "ML rejected setup below probability threshold"

        return MLFilterResult(
            signal_id=signal_id,
            decision=decision,
            probability=probability,
            threshold=self.config.min_probability,
            reduce_risk_threshold=self.config.reduce_risk_threshold,
            risk_multiplier=risk_multiplier,
            model_id=active_entry.model_id,
            model_name=active_entry.model_name,
            reason=reason,
            features_snapshot=features,
        )

    def _active_entry(self) -> ModelRegistryEntry | None:
        try:
            return self.registry.active_model()
        except (FileNotFoundError, KeyError, ValueError):
            return None

    @staticmethod
    def _predict_probability(model: Any, row: list[list[float]]) -> float:
        estimator = model.get("estimator") if isinstance(model, dict) else model
        if not hasattr(estimator, "predict_proba"):
            raise ValueError("Active ML model must expose predict_proba")
        raw = estimator.predict_proba(row)
        first = raw[0]
        if isinstance(first, (list, tuple)):
            probability = float(first[-1])
        elif hasattr(first, "__len__") and not isinstance(first, (float, int)):
            probability = float(first[-1])
        else:
            probability = float(first)
        return max(0.0, min(1.0, probability))


def build_signal_id(signal: SilverBulletSignal) -> str:
    """Build a stable local signal identifier for logs and ML predictions."""

    return "|".join(
        [
            signal.symbol,
            signal.timeframe,
            signal.direction.value,
            signal.generated_at.isoformat(),
        ]
    )
