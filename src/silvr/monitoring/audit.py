"""Structured JSON audit logging with secret redaction."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SENSITIVE_KEY_PARTS: tuple[str, ...] = (
    "api_key",
    "apikey",
    "secret",
    "token",
    "password",
    "passphrase",
    "private_key",
    "chat_id",
)


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Structured audit event."""

    event_type: str
    message: str
    level: str = "INFO"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable event dictionary."""

        return {
            "created_at": self.created_at.isoformat(),
            "level": self.level,
            "event_type": self.event_type,
            "message": self.message,
            "context": redact_secrets(self.context),
        }


class StructuredAuditLogger:
    """Write JSON-lines audit logs and retain in-memory events for tests."""

    def __init__(self, log_path: str | Path | None = None) -> None:
        self.log_path = Path(log_path) if log_path is not None else None
        self.events: list[AuditEvent] = []

    def log(
        self,
        event_type: str,
        message: str,
        *,
        level: str = "INFO",
        context: dict[str, Any] | None = None,
        created_at: datetime | None = None,
    ) -> AuditEvent:
        """Record one structured audit event."""

        event = AuditEvent(
            event_type=event_type,
            message=message,
            level=level,
            created_at=created_at or datetime.now(timezone.utc),
            context=redact_secrets(context or {}),
        )
        self.events.append(event)
        if self.log_path is not None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event.to_dict(), sort_keys=True) + "\n")
        return event


def redact_secrets(value: Any) -> Any:
    """Redact secret-looking fields from nested log context."""

    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(str(key)):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_secrets(item)
        return redacted
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item) for item in value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)
