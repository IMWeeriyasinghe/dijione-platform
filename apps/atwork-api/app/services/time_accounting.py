"""Pure working-time arithmetic: no database, no clock, no policy.

Every timestamp is whole-second aware UTC. Daily totals split elapsed time at
local midnight in the supplied time zone; the session record is never split.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo


class BreakLike(Protocol):
    started_at: datetime
    ended_at: datetime | None


class SessionLike(Protocol):
    check_in_at: datetime
    check_out_at: datetime | None
    breaks: Sequence[BreakLike]


@dataclass(frozen=True)
class Totals:
    gross_seconds: int = 0
    break_seconds: int = 0

    @property
    def net_seconds(self) -> int:
        return max(self.gross_seconds - self.break_seconds, 0)


def local_day_bounds(day: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    """The UTC instants of the start of ``day`` and of the next local day."""
    start = datetime.combine(day, time.min, zone)
    end = datetime.combine(day + timedelta(days=1), time.min, zone)
    return start.astimezone(ZoneInfo("UTC")), end.astimezone(ZoneInfo("UTC"))


def split_seconds_by_local_day(start: datetime, end: datetime, zone: ZoneInfo) -> dict[date, int]:
    result: dict[date, int] = {}
    cursor = start
    while cursor < end:
        day = cursor.astimezone(zone).date()
        boundary = min(local_day_bounds(day, zone)[1], end)
        result[day] = result.get(day, 0) + int((boundary - cursor).total_seconds())
        cursor = boundary
    return result


def _session_end(session: SessionLike, now: datetime) -> datetime:
    return session.check_out_at or now


def _break_interval(item: BreakLike, session_end: datetime) -> tuple[datetime, datetime]:
    return item.started_at, min(item.ended_at or session_end, session_end)


def session_totals(session: SessionLike, now: datetime) -> Totals:
    """Open sessions and open breaks are measured up to ``now``."""
    end = _session_end(session, now)
    gross = int((end - session.check_in_at).total_seconds())
    breaks = sum(int((stop - start).total_seconds()) for start, stop in (_break_interval(b, end) for b in session.breaks))
    return Totals(gross_seconds=gross, break_seconds=breaks)


def daily_totals(sessions: Iterable[SessionLike], zone: ZoneInfo, now: datetime) -> dict[date, Totals]:
    gross: dict[date, int] = {}
    breaks: dict[date, int] = {}
    for session in sessions:
        end = _session_end(session, now)
        for day, seconds in split_seconds_by_local_day(session.check_in_at, end, zone).items():
            gross[day] = gross.get(day, 0) + seconds
        for item in session.breaks:
            start, stop = _break_interval(item, end)
            for day, seconds in split_seconds_by_local_day(start, stop, zone).items():
                breaks[day] = breaks.get(day, 0) + seconds
    return {day: Totals(gross_seconds=seconds, break_seconds=breaks.get(day, 0)) for day, seconds in gross.items()}
