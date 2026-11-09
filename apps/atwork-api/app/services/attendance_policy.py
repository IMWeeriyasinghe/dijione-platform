"""Interim attendance policy. Approved future policies change only this file.

Deliberately absent: automatic closing, long-session limits, invented
timestamps, absence detection and automatic break deductions.
"""

from dataclasses import dataclass
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.core.errors import AttendanceError
from app.models.attendance import AttendanceSession


@dataclass(frozen=True)
class AttendancePolicy:
    business_time_zone: str

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.business_time_zone)

    def ensure_can_check_out(self, session: AttendanceSession) -> None:
        if any(item.ended_at is None for item in session.breaks):
            raise AttendanceError("BREAK_STILL_OPEN", "End your break before checking out.")


def get_policy() -> AttendancePolicy:
    return AttendancePolicy(business_time_zone=get_settings().business_time_zone)
