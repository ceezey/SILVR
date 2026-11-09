"""Silver Bullet session detection."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from silvr.strategy.models import SessionState, SessionWindow


DEFAULT_SESSIONS: tuple[SessionWindow, ...] = (
    SessionWindow("london", time(3, 0), time(4, 0), True),
    SessionWindow("new_york_am", time(10, 0), time(11, 0), True),
    SessionWindow("new_york_pm", time(14, 0), time(15, 0), False),
)


class SilverBulletSessionEngine:
    """Detect whether a timestamp is inside a configured Silver Bullet window."""

    def __init__(
        self,
        *,
        timezone_name: str = "America/New_York",
        sessions: tuple[SessionWindow, ...] = DEFAULT_SESSIONS,
    ) -> None:
        self.timezone_name = timezone_name
        try:
            self.timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            if timezone_name != "America/New_York":
                raise
            self.timezone = None
        self.sessions = sessions

    def evaluate(self, timestamp: datetime) -> SessionState:
        """Return active session state for a timestamp."""

        local_time = self._to_local(timestamp)
        for session in self.sessions:
            if not session.enabled:
                continue
            start_at = datetime.combine(local_time.date(), session.start, tzinfo=local_time.tzinfo)
            end_at = datetime.combine(local_time.date(), session.end, tzinfo=local_time.tzinfo)
            if start_at <= local_time < end_at:
                return SessionState(
                    is_active=True,
                    name=session.name,
                    timezone=self.timezone_name,
                    start_at=start_at,
                    end_at=end_at,
                )
        return SessionState(is_active=False, name=None, timezone=self.timezone_name)

    def _to_local(self, timestamp: datetime) -> datetime:
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        if self.timezone is not None:
            return timestamp.astimezone(self.timezone)

        utc_timestamp = timestamp.astimezone(UTC)
        offset_hours = -4 if _is_new_york_dst_utc(utc_timestamp) else -5
        fallback_timezone = timezone(timedelta(hours=offset_hours), self.timezone_name)
        return utc_timestamp.astimezone(fallback_timezone)


def _is_new_york_dst_utc(timestamp: datetime) -> bool:
    """Return whether a UTC timestamp is in US Eastern daylight time."""

    year = timestamp.year
    dst_start = _nth_weekday_utc(year, month=3, weekday=6, occurrence=2, hour=7)
    dst_end = _nth_weekday_utc(year, month=11, weekday=6, occurrence=1, hour=6)
    return dst_start <= timestamp < dst_end


def _nth_weekday_utc(
    year: int,
    *,
    month: int,
    weekday: int,
    occurrence: int,
    hour: int,
) -> datetime:
    current = datetime(year, month, 1, hour, tzinfo=UTC)
    days_until_weekday = (weekday - current.weekday()) % 7
    day = 1 + days_until_weekday + (occurrence - 1) * 7
    return datetime(year, month, day, hour, tzinfo=UTC)
