"""Dashboard data export helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_dashboard_data(
    *,
    daily_report: dict[str, Any],
    weekly_report: dict[str, Any],
    recent_trades: list[dict[str, Any]],
    recent_rejections: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a compact dashboard-ready data payload."""

    return {
        "daily": daily_report,
        "weekly": weekly_report,
        "recent_trades": recent_trades,
        "recent_rejections": recent_rejections,
    }


def export_dashboard_data(payload: dict[str, Any], path: str | Path) -> Path:
    """Write dashboard data as JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output_path
