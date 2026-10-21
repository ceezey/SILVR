"""Per-run simulated kill switch for backtests, reset at each new UTC day.

The reset lives here, in the backtest layer, on purpose. `KillSwitch` and
`RiskManagementEngine` have no reset path, so paper, demo and live code cannot
clear a trip. The constructor takes no path, so this switch can never point at
the real kill-switch file.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from silver_bot.risk.kill_switch import KillSwitch

KILL_SWITCH_FILENAME = "KILL_SWITCH"
REPORT_MODE = "simulated_per_run_daily_reset"


class SimulatedKillSwitch(KillSwitch):
    """A kill switch in its own temporary directory that records every trip."""

    def __init__(self) -> None:
        super().__init__(None)
        self.now: datetime | None = None
        self.trips: list[dict[str, Any]] = []
        self._scratch: tempfile.TemporaryDirectory[str] | None = None

    def __enter__(self) -> SimulatedKillSwitch:
        self._scratch = tempfile.TemporaryDirectory()
        self.path = Path(self._scratch.name) / KILL_SWITCH_FILENAME
        return self

    def __exit__(self, *exc_info: object) -> None:
        if self._scratch is not None:
            self._scratch.cleanup()
            self._scratch = None

    def trip(self, reason: str) -> None:
        """Trip like `KillSwitch.trip`, and log the simulated time of a new trip."""

        was_active = self.is_active()
        super().trip(reason)
        if not was_active and self.is_active():
            self.trips.append({"reason": reason, "tripped_at": self.now, "reset_at": None})

    def reset_if_new_day(self, at: datetime) -> bool:
        """Clear the trip when `at` falls on a later UTC day than the trip."""

        if self.path is None or not self.trips or not self.is_active():
            return False
        last = self.trips[-1]
        tripped_at = last["tripped_at"]
        if last["reset_at"] is not None or tripped_at is None:
            return False
        if at.astimezone(UTC).date() <= tripped_at.astimezone(UTC).date():
            return False
        self.path.unlink(missing_ok=True)
        last["reset_at"] = at
        return True

    def report(self) -> dict[str, Any]:
        """Return the trip count and log for the backtest reports."""

        return {
            "mode": REPORT_MODE,
            "trips": len(self.trips),
            "trip_log": [
                {
                    "reason": trip["reason"],
                    "tripped_at": _iso(trip["tripped_at"]),
                    "reset_at": _iso(trip["reset_at"]),
                }
                for trip in self.trips
            ],
        }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
