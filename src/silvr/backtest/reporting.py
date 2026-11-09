"""Backtest export helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def json_safe(value: Any) -> Any:
    """Return a JSON-serialisable copy: datetimes as ISO text, inf as \"inf\", enums as values."""

    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if value == float("inf"):
        return "inf"
    if hasattr(value, "value"):
        return value.value
    return value
