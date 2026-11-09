"""Calibration reporting for setup outcome classifiers."""

from __future__ import annotations

import csv
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CalibrationBin:
    """One probability bucket in a reliability table."""

    bin_index: int
    lower_bound: float
    upper_bound: float
    sample_count: int
    mean_predicted_probability: float
    actual_win_rate: float
    absolute_error: float

    def to_dict(self) -> dict[str, float | int]:
        """Serialize the bin for JSON or CSV export."""

        return {
            "bin_index": self.bin_index,
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
            "sample_count": self.sample_count,
            "mean_predicted_probability": self.mean_predicted_probability,
            "actual_win_rate": self.actual_win_rate,
            "absolute_error": self.absolute_error,
        }


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    """Probability calibration summary for a classifier."""

    sample_count: int
    brier_score: float
    expected_calibration_error: float
    bins: tuple[CalibrationBin, ...]

    def to_dict(self) -> dict[str, object]:
        """Serialize the report for JSON export."""

        return {
            "sample_count": self.sample_count,
            "brier_score": self.brier_score,
            "expected_calibration_error": self.expected_calibration_error,
            "bin_count": len(self.bins),
            "bins": [item.to_dict() for item in self.bins],
        }


def build_calibration_report(
    probabilities: Sequence[float],
    labels: Sequence[int],
    *,
    bin_count: int = 10,
) -> CalibrationReport:
    """Compare predicted probabilities with realized binary outcomes."""

    clean_probabilities = [float(value) for value in probabilities]
    clean_labels = [int(value) for value in labels]
    _validate_inputs(clean_probabilities, clean_labels, bin_count)

    sample_count = len(clean_labels)
    brier_score = sum(
        (probability - label) ** 2
        for probability, label in zip(clean_probabilities, clean_labels, strict=True)
    ) / sample_count
    bins = _build_bins(clean_probabilities, clean_labels, bin_count)
    expected_calibration_error = sum(
        (item.sample_count / sample_count) * item.absolute_error
        for item in bins
        if item.sample_count
    )
    return CalibrationReport(
        sample_count=sample_count,
        brier_score=brier_score,
        expected_calibration_error=expected_calibration_error,
        bins=tuple(bins),
    )


def export_calibration_report(
    report: CalibrationReport,
    output_dir: Path,
) -> dict[str, Path]:
    """Export calibration JSON and reliability-bin CSV files."""

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "calibration_report.json"
    bins_path = output_dir / "calibration_bins.csv"

    report_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    with bins_path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "bin_index",
            "lower_bound",
            "upper_bound",
            "sample_count",
            "mean_predicted_probability",
            "actual_win_rate",
            "absolute_error",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in report.bins:
            writer.writerow(item.to_dict())

    return {
        "report": report_path,
        "bins": bins_path,
    }


def _validate_inputs(
    probabilities: Sequence[float],
    labels: Sequence[int],
    bin_count: int,
) -> None:
    if bin_count < 1:
        raise ValueError("bin_count must be positive")
    if not probabilities:
        raise ValueError("probabilities and labels cannot be empty")
    if len(probabilities) != len(labels):
        raise ValueError("probabilities and labels must have the same length")
    invalid_probabilities = [value for value in probabilities if value < 0.0 or value > 1.0]
    if invalid_probabilities:
        raise ValueError("probabilities must be between 0 and 1")
    invalid_labels = [value for value in labels if value not in {0, 1}]
    if invalid_labels:
        raise ValueError("labels must be binary values: 0 or 1")


def _build_bins(
    probabilities: Sequence[float],
    labels: Sequence[int],
    bin_count: int,
) -> list[CalibrationBin]:
    bins: list[CalibrationBin] = []
    for index in range(bin_count):
        lower_bound = index / bin_count
        upper_bound = (index + 1) / bin_count
        members = [
            (probability, label)
            for probability, label in zip(probabilities, labels, strict=True)
            if _in_bin(probability, lower_bound, upper_bound, is_final=index == bin_count - 1)
        ]
        sample_count = len(members)
        if sample_count:
            mean_probability = sum(item[0] for item in members) / sample_count
            actual_win_rate = sum(item[1] for item in members) / sample_count
        else:
            mean_probability = 0.0
            actual_win_rate = 0.0
        bins.append(
            CalibrationBin(
                bin_index=index,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
                sample_count=sample_count,
                mean_predicted_probability=mean_probability,
                actual_win_rate=actual_win_rate,
                absolute_error=abs(mean_probability - actual_win_rate) if sample_count else 0.0,
            )
        )
    return bins


def _in_bin(
    probability: float,
    lower_bound: float,
    upper_bound: float,
    *,
    is_final: bool,
) -> bool:
    if is_final:
        return lower_bound <= probability <= upper_bound
    return lower_bound <= probability < upper_bound
