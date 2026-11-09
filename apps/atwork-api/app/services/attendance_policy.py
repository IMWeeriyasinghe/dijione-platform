"""Interim attendance policy. Approved future policies change only this file.

Deliberately absent: automatic closing, long-session limits, invented
timestamps, absence detection and automatic break deductions.
"""

from dataclasses import dataclass
from zoneinfo import ZoneInfo

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import WORK_MODES
from app.core.errors import AttendanceError
from app.db.session import get_db
from app.models.attendance import AttendanceSession
from app.models.corrections import AtworkSettings

DEFAULT_MISSED_CHECKOUT_HOURS = 12
DEFAULT_TIME_FORMAT = "24h"
DEFAULT_HISTORY_DAYS = 30


@dataclass(frozen=True)
class AttendancePolicy:
    business_time_zone: str
    enabled_work_modes: tuple[str, ...] = WORK_MODES
    missed_checkout_hours: int = DEFAULT_MISSED_CHECKOUT_HOURS
    time_format: str = DEFAULT_TIME_FORMAT
    default_history_days: int = DEFAULT_HISTORY_DAYS
    settings_version: int = 0

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.business_time_zone)

    def ensure_can_check_out(self, session: AttendanceSession) -> None:
        if any(item.ended_at is None for item in session.breaks):
            raise AttendanceError("BREAK_STILL_OPEN", "End your break before checking out.")

    def ensure_mode_enabled(self, work_mode: str) -> None:
        if work_mode not in self.enabled_work_modes:
            raise AttendanceError("WORK_MODE_DISABLED", "This work mode is not currently available.", 422)


def get_policy(db: Session = Depends(get_db)) -> AttendancePolicy:
    """Saved settings win; with none saved, the deployment defaults apply."""
    row = db.get(AtworkSettings, 1)
    if row is None:
        return AttendancePolicy(business_time_zone=get_settings().business_time_zone)
    return AttendancePolicy(
        business_time_zone=row.business_time_zone,
        enabled_work_modes=tuple(row.enabled_work_modes),
        missed_checkout_hours=row.missed_checkout_hours,
        time_format=row.time_format,
        default_history_days=row.default_history_days,
        settings_version=row.version,
    )
