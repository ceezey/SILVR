"""Model promotion policy for offline ML validation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class PromotionDecision(str, Enum):
    """Allowed model promotion outcomes."""

    PROMOTE = "promote"
    REJECT = "reject"
    KEEP_CURRENT = "keep_current"


@dataclass(frozen=True, slots=True)
class PromotionPolicyConfig:
    """Configurable acceptance criteria for a candidate classifier."""

    primary_metric: str = "accuracy"
    minimum_validation_improvement: float = 0.0
    maximum_test_score_degradation: float = 0.02
    maximum_brier_score: float = 0.25
    minimum_sample_count: int = 30

    def __post_init__(self) -> None:
        if not self.primary_metric:
            raise ValueError("primary_metric cannot be empty")
        if self.minimum_validation_improvement < 0:
            raise ValueError("minimum_validation_improvement cannot be negative")
        if self.maximum_test_score_degradation < 0:
            raise ValueError("maximum_test_score_degradation cannot be negative")
        if not 0 <= self.maximum_brier_score <= 1:
            raise ValueError("maximum_brier_score must be between 0 and 1")
        if self.minimum_sample_count < 1:
            raise ValueError("minimum_sample_count must be positive")


@dataclass(frozen=True, slots=True)
class PromotionDecisionResult:
    """Decision and audit reasons for a candidate model."""

    decision: PromotionDecision
    candidate_model_id: str | None
    current_model_id: str | None
    reasons: tuple[str, ...]
    policy: dict[str, float | int | str]
    candidate_metrics: dict[str, Any] = field(default_factory=dict)
    current_metrics: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Serialize the promotion decision for JSON export."""

        return {
            "decision": self.decision.value,
            "candidate_model_id": self.candidate_model_id,
            "current_model_id": self.current_model_id,
            "reasons": list(self.reasons),
            "policy": self.policy,
            "candidate_metrics": self.candidate_metrics,
            "current_metrics": self.current_metrics,
            "created_at": self.created_at,
        }


def evaluate_model_promotion(
    *,
    candidate_metrics: Mapping[str, Any] | None,
    current_metrics: Mapping[str, Any] | None = None,
    candidate_model_id: str | None = None,
    current_model_id: str | None = None,
    config: PromotionPolicyConfig | None = None,
) -> PromotionDecisionResult:
    """Evaluate whether a candidate model may replace the current active model."""

    policy = config or PromotionPolicyConfig()
    if candidate_metrics is None:
        return _result(
            PromotionDecision.KEEP_CURRENT,
            candidate_model_id,
            current_model_id,
            ["No candidate model metrics supplied; keeping current model"],
            policy,
            {},
            dict(current_metrics or {}),
        )

    candidate = dict(candidate_metrics)
    current = dict(current_metrics or {})
    reasons: list[str] = []
    if _bool_metric(candidate, "used_final_test_for_optimization"):
        reasons.append("Candidate used final test data for optimization")

    candidate_validation_score = _metric_value(candidate, "validation_metrics", policy.primary_metric)
    if candidate_validation_score is None:
        reasons.append(f"Candidate validation metric missing: {policy.primary_metric}")

    candidate_test_score = _metric_value(candidate, "test_metrics", policy.primary_metric)
    if candidate_test_score is None:
        reasons.append(f"Candidate test metric missing: {policy.primary_metric}")

    candidate_brier_score = _calibration_value(candidate, "brier_score")
    if candidate_brier_score is None:
        reasons.append("Candidate Brier score missing")
    elif candidate_brier_score > policy.maximum_brier_score:
        reasons.append(
            "Candidate Brier score exceeds policy limit "
            f"({candidate_brier_score:.6f} > {policy.maximum_brier_score:.6f})"
        )

    sample_count = _minimum_available_sample_count(candidate)
    if sample_count is None:
        reasons.append("Candidate sample count missing")
    elif sample_count < policy.minimum_sample_count:
        reasons.append(
            "Candidate sample count below policy minimum "
            f"({sample_count} < {policy.minimum_sample_count})"
        )

    current_validation_score = _metric_value(current, "validation_metrics", policy.primary_metric)
    current_test_score = _metric_value(current, "test_metrics", policy.primary_metric)
    has_active_model = current_metrics is not None
    if has_active_model and candidate_validation_score is not None and current_validation_score is not None:
        required_score = current_validation_score + policy.minimum_validation_improvement
        if candidate_validation_score < required_score:
            reasons.append(
                "Candidate validation score is not better than current active model "
                f"({candidate_validation_score:.6f} < required {required_score:.6f})"
            )
        elif candidate_validation_score == current_validation_score and not reasons:
            return _result(
                PromotionDecision.KEEP_CURRENT,
                candidate_model_id,
                current_model_id,
                ["Candidate validation score ties current active model; keeping current model"],
                policy,
                candidate,
                current,
            )
    elif has_active_model and current_validation_score is None:
        reasons.append(f"Current active validation metric missing: {policy.primary_metric}")

    if has_active_model and candidate_test_score is not None and current_test_score is not None:
        allowed_floor = current_test_score - policy.maximum_test_score_degradation
        if candidate_test_score < allowed_floor:
            reasons.append(
                "Candidate test score degrades beyond policy limit "
                f"({candidate_test_score:.6f} < allowed {allowed_floor:.6f})"
            )
    elif has_active_model and current_test_score is None:
        reasons.append(f"Current active test metric missing: {policy.primary_metric}")

    if reasons:
        return _result(
            PromotionDecision.REJECT,
            candidate_model_id,
            current_model_id,
            reasons,
            policy,
            candidate,
            current,
        )

    success_reasons = ["Candidate passes model promotion policy"]
    if not has_active_model:
        success_reasons.append("No active model exists; candidate may become active")
    return _result(
        PromotionDecision.PROMOTE,
        candidate_model_id,
        current_model_id,
        success_reasons,
        policy,
        candidate,
        current,
    )


def export_promotion_decision(result: PromotionDecisionResult, output_path: Path) -> Path:
    """Write a promotion decision audit file."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    return output_path


def _result(
    decision: PromotionDecision,
    candidate_model_id: str | None,
    current_model_id: str | None,
    reasons: list[str],
    policy: PromotionPolicyConfig,
    candidate_metrics: dict[str, Any],
    current_metrics: dict[str, Any],
) -> PromotionDecisionResult:
    return PromotionDecisionResult(
        decision=decision,
        candidate_model_id=candidate_model_id,
        current_model_id=current_model_id,
        reasons=tuple(reasons),
        policy={
            "primary_metric": policy.primary_metric,
            "minimum_validation_improvement": policy.minimum_validation_improvement,
            "maximum_test_score_degradation": policy.maximum_test_score_degradation,
            "maximum_brier_score": policy.maximum_brier_score,
            "minimum_sample_count": policy.minimum_sample_count,
        },
        candidate_metrics=candidate_metrics,
        current_metrics=current_metrics,
    )


def _metric_value(metrics: Mapping[str, Any], section: str, metric_name: str) -> float | None:
    section_payload = metrics.get(section)
    if isinstance(section_payload, Mapping) and metric_name in section_payload:
        return float(section_payload[metric_name])
    if metric_name in metrics:
        return float(metrics[metric_name])
    return None


def _calibration_value(metrics: Mapping[str, Any], metric_name: str) -> float | None:
    calibration_payload = metrics.get("calibration")
    if isinstance(calibration_payload, Mapping) and metric_name in calibration_payload:
        return float(calibration_payload[metric_name])
    if metric_name in metrics:
        return float(metrics[metric_name])
    return None


def _minimum_available_sample_count(metrics: Mapping[str, Any]) -> int | None:
    counts: list[int] = []
    for section in ("validation_metrics", "test_metrics", "calibration"):
        section_payload = metrics.get(section)
        if isinstance(section_payload, Mapping) and "sample_count" in section_payload:
            counts.append(int(section_payload["sample_count"]))
    if "sample_count" in metrics:
        counts.append(int(metrics["sample_count"]))
    return min(counts) if counts else None


def _bool_metric(metrics: Mapping[str, Any], metric_name: str) -> bool:
    value = metrics.get(metric_name)
    if value is not None:
        return bool(value)
    metadata = metrics.get("metadata")
    if isinstance(metadata, Mapping) and metric_name in metadata:
        return bool(metadata[metric_name])
    return False
