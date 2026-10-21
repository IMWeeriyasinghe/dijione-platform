"""Neutral daily attendance facts, computed on read (never persisted in V1).

Facts only: first activity, latest activity, punch count, span, terminals,
plus neutral "needs review" flags. No Present/Absent/Late/Early/worked
hours — those require an approved attendance policy (Phase 3).
``PunchState`` is never interpreted.
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import date

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import IdentityClass, ReviewFlag
from app.repositories.attendance_repository import AttendanceRepository
from app.services.identity_match_service import classify
from app.services.time_derivation import site_today
from app.services.workforce_directory import DirectorySnapshot

_IDENTITY_FLAG = {
    IdentityClass.UNMATCHED: ReviewFlag.UNMATCHED_CODE,
    IdentityClass.AMBIGUOUS: ReviewFlag.AMBIGUOUS_CODE,
    IdentityClass.MATCHED_INACTIVE: ReviewFlag.INACTIVE_EMPLOYEE_ACTIVITY,
    IdentityClass.MATCHED_BEFORE_HIRE: ReviewFlag.BEFORE_HIRE_ACTIVITY,
}


def daily_activity(
    db: Session, *, allowed_site_ids: Collection[str], site_id: str, site_time_zone: str | None,
    date_from: date, date_to: date, directory: DirectorySnapshot, today: date | None = None,
) -> list[dict]:
    settings = get_settings()
    repo = AttendanceRepository(db)
    groups = repo.daily_groups(allowed_site_ids=allowed_site_ids, site_id=site_id, date_from=date_from, date_to=date_to)

    dup_keys: set[tuple[date, str]] = set()
    previous: dict[tuple[date, str], object] = {}
    for local_date, code, utc in repo.punch_times(
        allowed_site_ids=allowed_site_ids, site_id=site_id, date_from=date_from, date_to=date_to
    ):
        key = (local_date, code)
        prev = previous.get(key)
        if prev is not None and (utc - prev).total_seconds() <= settings.duplicate_tap_seconds:
            dup_keys.add(key)
        previous[key] = utc

    today = today or site_today(site_time_zone)
    index = directory.by_employee_number() if directory.available else {}
    out = []
    for _site, local_date, code, count, first, last, terminals, inconsistent in groups:
        flags: list[str] = []
        if count == 1 and local_date < today:
            flags.append(ReviewFlag.SINGLE_PUNCH.value)
        if count >= settings.high_punch_count_threshold:
            flags.append(ReviewFlag.HIGH_PUNCH_COUNT.value)
        if (local_date, code) in dup_keys:
            flags.append(ReviewFlag.POSSIBLE_DUPLICATE_TAP.value)
        identity = None
        if directory.available:
            identity = classify(index.get(code, []), local_date, local_date)
            if identity in _IDENTITY_FLAG:
                flags.append(_IDENTITY_FLAG[identity].value)
        if inconsistent:
            flags.append(ReviewFlag.TZ_INCONSISTENT.value)
        out.append({
            "site_id": site_id, "local_date": local_date.isoformat(), "emp_code": code,
            "first_activity_utc": first.isoformat(), "latest_activity_utc": last.isoformat(),
            "punch_count": count, "span_minutes": int((last - first).total_seconds() // 60),
            "terminals": terminals, "identity_class": identity.value if identity else None,
            "flags": flags,
        })
    return out
