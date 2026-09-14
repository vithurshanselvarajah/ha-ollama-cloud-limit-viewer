from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


class _BaseResetTracker:
    RESET_FRACTION = 0.5

    def __init__(self) -> None:
        self._last_usage: float | None = None
        self._anchor: datetime | None = None

    @property
    def has_anchor(self) -> bool:
        return self._anchor is not None

    def observe(self, usage_usd: float, now: datetime) -> bool:
        last = self._last_usage
        self._last_usage = usage_usd

        if last is None:
            return False

        if last <= 0:
            return False

        if usage_usd < last * self.RESET_FRACTION:
            boundary = self._boundary_for(now)
            self._anchor = boundary
            return True

        return False

    def next_reset(self, now: datetime) -> datetime | None:
        if self._anchor is None:
            return None
        boundary = self._boundary_for(now)
        if boundary <= now:
            boundary = self._advance(boundary)
        boundary = max(boundary, self._anchor)
        return boundary

    def _boundary_for(self, now: datetime) -> datetime: ...
    def _advance(self, boundary: datetime) -> datetime: ...


@dataclass(frozen=True)
class _UTCMidnight:
    dt: datetime

    @classmethod
    def of(cls, dt: datetime) -> _UTCMidnight:
        return cls(dt.astimezone(UTC))


class SessionResetTracker(_BaseResetTracker):
    BUCKET_HOURS = 5

    def _boundary_for(self, now: datetime) -> datetime:
        now = _UTCMidnight.of(now).dt
        bucket_index = now.hour // self.BUCKET_HOURS
        return now.replace(
            hour=bucket_index * self.BUCKET_HOURS,
            minute=0,
            second=0,
            microsecond=0,
        )

    def _advance(self, boundary: datetime) -> datetime:
        return boundary + timedelta(hours=self.BUCKET_HOURS)


class WeeklyResetTracker(_BaseResetTracker):
    def _boundary_for(self, now: datetime) -> datetime:
        now = _UTCMidnight.of(now).dt
        days_since_monday = now.weekday()
        monday = (now - timedelta(days=days_since_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return monday

    def _advance(self, boundary: datetime) -> datetime:
        return boundary + timedelta(days=7)
