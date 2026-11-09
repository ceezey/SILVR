"""Machine-learning foundation for rule-based setup filtering.

ML code in this package builds labels, features, and offline model artifacts.
It does not generate signals, place orders, or bypass risk management.
"""

from silvr.ml.dataset import (
    MLDataset,
    MLDatasetBuilder,
    MLDatasetSplit,
    MLSetupRow,
    label_signal_outcome,
    time_based_split,
)
from silvr.ml.calibration import (
    CalibrationBin,
    CalibrationReport,
    build_calibration_report,
    export_calibration_report,
)
from silvr.ml.features import (
    FEATURE_NAMES,
    LEAKAGE_COLUMN_KEYWORDS,
    FeatureEngineeringPipeline,
    validate_no_future_leakage_columns,
)
from silvr.ml.filter import (
    MLDecision,
    MLFilterConfig,
    MLFilterResult,
    MLProbabilityFilter,
    build_signal_id,
)
from silvr.ml.promotion import (
    PromotionDecision,
    PromotionDecisionResult,
    PromotionPolicyConfig,
    evaluate_model_promotion,
    export_promotion_decision,
)
from silvr.ml.registry import ModelRegistry, ModelRegistryEntry
from silvr.ml.training import (
    BaselineTrainingResult,
    SimpleLogisticRegressionModel,
    train_baseline_models,
)

__all__ = [
    "FEATURE_NAMES",
    "LEAKAGE_COLUMN_KEYWORDS",
    "BaselineTrainingResult",
    "CalibrationBin",
    "CalibrationReport",
    "FeatureEngineeringPipeline",
    "MLDataset",
    "MLDatasetBuilder",
    "MLDatasetSplit",
    "MLDecision",
    "MLFilterConfig",
    "MLFilterResult",
    "MLProbabilityFilter",
    "MLSetupRow",
    "ModelRegistry",
    "ModelRegistryEntry",
    "PromotionDecision",
    "PromotionDecisionResult",
    "PromotionPolicyConfig",
    "SimpleLogisticRegressionModel",
    "build_signal_id",
    "build_calibration_report",
    "evaluate_model_promotion",
    "export_calibration_report",
    "export_promotion_decision",
    "label_signal_outcome",
    "time_based_split",
    "train_baseline_models",
    "validate_no_future_leakage_columns",
]
