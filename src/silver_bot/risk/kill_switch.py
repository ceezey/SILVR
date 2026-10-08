"""File-based safety kill switch."""

from __future__ import annotations

from pathlib import Path


class KillSwitch:
    """Checks whether a manual kill-switch file exists."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else None

    def is_active(self) -> bool:
        """Return true when the configured kill-switch file exists."""

        return self.path is not None and self.path.exists()
