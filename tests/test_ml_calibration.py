import csv
import json
from pathlib import Path

import pytest

from silver_bot.ml import build_calibration_report, export_calibration_report


def test_calibration_report_calculates_brier_bins_and_ece() -> None:
    report = build_calibration_report(
        probabilities=[0.1, 0.2, 0.8, 0.9],
        labels=[0, 0, 1, 1],
        bin_count=2,
    )

    assert report.sample_count == 4
    assert report.brier_score == pytest.approx(0.025)
    assert report.expected_calibration_error == pytest.approx(0.15)
    assert report.bins[0].sample_count == 2
    assert report.bins[0].mean_predicted_probability == pytest.approx(0.15)
    assert report.bins[0].actual_win_rate == 0.0
    assert report.bins[1].sample_count == 2
    assert report.bins[1].mean_predicted_probability == pytest.approx(0.85)
    assert report.bins[1].actual_win_rate == 1.0


def test_calibration_report_exports_json_and_csv(tmp_path: Path) -> None:
    report = build_calibration_report(
        probabilities=[0.05, 0.45, 0.55, 1.0],
        labels=[0, 1, 0, 1],
        bin_count=2,
    )

    paths = export_calibration_report(report, tmp_path)

    assert paths["report"].name == "calibration_report.json"
    assert paths["bins"].name == "calibration_bins.csv"
    payload = json.loads(paths["report"].read_text(encoding="utf-8"))
    assert payload["sample_count"] == 4
    assert payload["bin_count"] == 2
    with paths["bins"].open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["bin_index"] == "0"
    assert rows[1]["sample_count"] == "2"


def test_calibration_report_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="same length"):
        build_calibration_report([0.4], [1, 0])
    with pytest.raises(ValueError, match="between 0 and 1"):
        build_calibration_report([1.2], [1])
    with pytest.raises(ValueError, match="binary"):
        build_calibration_report([0.5], [2])
