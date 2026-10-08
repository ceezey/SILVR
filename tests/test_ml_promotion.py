import json
from pathlib import Path

from silver_bot.ml import (
    PromotionDecision,
    PromotionPolicyConfig,
    evaluate_model_promotion,
    export_promotion_decision,
)


def policy() -> PromotionPolicyConfig:
    return PromotionPolicyConfig(
        primary_metric="accuracy",
        minimum_validation_improvement=0.01,
        maximum_test_score_degradation=0.03,
        maximum_brier_score=0.20,
        minimum_sample_count=10,
    )


def metrics(
    *,
    validation_score: float,
    test_score: float,
    brier_score: float,
    sample_count: int = 100,
    optimized_on_final_test: bool = False,
) -> dict[str, object]:
    return {
        "validation_metrics": {
            "accuracy": validation_score,
            "sample_count": sample_count,
        },
        "test_metrics": {
            "accuracy": test_score,
            "sample_count": sample_count,
        },
        "calibration": {
            "brier_score": brier_score,
            "sample_count": sample_count,
        },
        "used_final_test_for_optimization": optimized_on_final_test,
    }


def test_candidate_model_is_promoted_when_policy_passes(tmp_path: Path) -> None:
    result = evaluate_model_promotion(
        candidate_metrics=metrics(validation_score=0.66, test_score=0.60, brier_score=0.12),
        current_metrics=metrics(validation_score=0.64, test_score=0.62, brier_score=0.15),
        candidate_model_id="candidate",
        current_model_id="active",
        config=policy(),
    )

    assert result.decision == PromotionDecision.PROMOTE
    assert "passes" in result.reasons[0]
    path = export_promotion_decision(result, tmp_path / "promotion_decision.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["decision"] == "promote"
    assert payload["candidate_model_id"] == "candidate"


def test_candidate_model_rejected_due_to_worse_validation_metric() -> None:
    result = evaluate_model_promotion(
        candidate_metrics=metrics(validation_score=0.62, test_score=0.63, brier_score=0.12),
        current_metrics=metrics(validation_score=0.64, test_score=0.62, brier_score=0.15),
        config=policy(),
    )

    assert result.decision == PromotionDecision.REJECT
    assert any("validation score" in reason for reason in result.reasons)


def test_candidate_model_rejected_due_to_test_score_degradation() -> None:
    result = evaluate_model_promotion(
        candidate_metrics=metrics(validation_score=0.70, test_score=0.55, brier_score=0.12),
        current_metrics=metrics(validation_score=0.64, test_score=0.62, brier_score=0.15),
        config=policy(),
    )

    assert result.decision == PromotionDecision.REJECT
    assert any("test score" in reason for reason in result.reasons)


def test_candidate_model_rejected_due_to_poor_calibration() -> None:
    result = evaluate_model_promotion(
        candidate_metrics=metrics(validation_score=0.70, test_score=0.68, brier_score=0.31),
        current_metrics=metrics(validation_score=0.64, test_score=0.62, brier_score=0.15),
        config=policy(),
    )

    assert result.decision == PromotionDecision.REJECT
    assert any("Brier score" in reason for reason in result.reasons)


def test_candidate_model_rejected_due_to_insufficient_samples() -> None:
    result = evaluate_model_promotion(
        candidate_metrics=metrics(
            validation_score=0.70,
            test_score=0.68,
            brier_score=0.12,
            sample_count=5,
        ),
        current_metrics=metrics(validation_score=0.64, test_score=0.62, brier_score=0.15),
        config=policy(),
    )

    assert result.decision == PromotionDecision.REJECT
    assert any("sample count" in reason for reason in result.reasons)


def test_no_active_model_fallback_promotes_valid_candidate() -> None:
    result = evaluate_model_promotion(
        candidate_metrics=metrics(validation_score=0.61, test_score=0.59, brier_score=0.14),
        current_metrics=None,
        candidate_model_id="candidate",
        config=policy(),
    )

    assert result.decision == PromotionDecision.PROMOTE
    assert any("No active model" in reason for reason in result.reasons)


def test_no_candidate_metrics_keeps_current_model() -> None:
    result = evaluate_model_promotion(
        candidate_metrics=None,
        current_metrics=metrics(validation_score=0.64, test_score=0.62, brier_score=0.15),
        current_model_id="active",
        config=policy(),
    )

    assert result.decision == PromotionDecision.KEEP_CURRENT
    assert any("No candidate" in reason for reason in result.reasons)


def test_tied_candidate_with_policy_failure_is_rejected() -> None:
    result = evaluate_model_promotion(
        candidate_metrics=metrics(validation_score=0.64, test_score=0.62, brier_score=0.31),
        current_metrics=metrics(validation_score=0.64, test_score=0.62, brier_score=0.15),
        config=PromotionPolicyConfig(
            primary_metric="accuracy",
            minimum_validation_improvement=0.0,
            maximum_test_score_degradation=0.03,
            maximum_brier_score=0.20,
            minimum_sample_count=10,
        ),
    )

    assert result.decision == PromotionDecision.REJECT
    assert any("Brier score" in reason for reason in result.reasons)


def test_candidate_rejected_if_final_test_was_used_for_optimization() -> None:
    result = evaluate_model_promotion(
        candidate_metrics=metrics(
            validation_score=0.70,
            test_score=0.68,
            brier_score=0.12,
            optimized_on_final_test=True,
        ),
        current_metrics=metrics(validation_score=0.64, test_score=0.62, brier_score=0.15),
        config=policy(),
    )

    assert result.decision == PromotionDecision.REJECT
    assert any("final test" in reason for reason in result.reasons)
