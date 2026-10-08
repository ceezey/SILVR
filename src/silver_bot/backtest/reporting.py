"""Backtest export helpers."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from silver_bot.backtest.models import BacktestResult


def export_backtest_result(result: BacktestResult, output_dir: str | Path) -> dict[str, Path]:
    """Export trades, equity, report, and rejected signals."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "trades": directory / "trades.csv",
        "equity_curve": directory / "equity_curve.csv",
        "backtest_report": directory / "backtest_report.json",
        "rejected_signals": directory / "rejected_signals.csv",
    }

    _write_csv(paths["trades"], result.trades)
    _write_csv(paths["equity_curve"], result.equity_curve)
    _write_csv(paths["rejected_signals"], result.rejected_signals)
    paths["backtest_report"].write_text(
        json.dumps(_json_safe(result.metrics), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return paths


def _write_csv(path: Path, rows: list[Any]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    first = rows[0]
    fieldnames = list(asdict(first).keys()) if is_dataclass(first) else list(first.keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            raw = asdict(row) if is_dataclass(row) else dict(row)
            writer.writerow({key: _csv_safe(value) for key, value in raw.items()})


def _csv_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    return value


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if value == float("inf"):
        return "inf"
    if hasattr(value, "value"):
        return value.value
    return value
