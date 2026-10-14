"""File-based safety kill switch."""

from __future__ import annotations

import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path


class KillSwitch:
    """Manual and automatic trading halt backed by a file.

    The switch fails closed: if the file exists, is a directory, or cannot be
    checked, trading is halted. Without a path the switch is still armed: a
    trip halts this instance in memory until it is discarded.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self.tripped_reason: str | None = None

    def is_active(self) -> bool:
        """Return true when trading must halt."""

        if self.path is None:
            return self.tripped_reason is not None
        try:
            os.stat(self.path)
        except FileNotFoundError:
            return self._ancestor_blocks_path(self.path)
        except OSError:
            return True
        return True

    @staticmethod
    def _ancestor_blocks_path(path: Path) -> bool:
        """Return true when the nearest existing ancestor is not a usable directory.

        Windows reports a regular-file parent as "path not found" rather than
        NotADirectoryError, so the ancestors are checked explicitly.
        """

        for ancestor in path.parents:
            try:
                mode = os.stat(ancestor).st_mode
            except FileNotFoundError:
                continue
            except OSError:
                return True
            return not stat.S_ISDIR(mode)
        return False

    def trip(self, reason: str) -> None:
        """Write the kill-switch file; the first trip's reason is kept."""

        if self.is_active():
            return
        if self.path is None:
            self.tripped_reason = reason
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"reason": reason, "tripped_at": datetime.now(timezone.utc).isoformat()}
        self.path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
