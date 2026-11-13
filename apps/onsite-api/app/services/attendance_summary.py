"""Neutral daily attendance facts, computed on read (never persisted in V1).

Facts only: first activity, latest activity, punch count, span, terminals,
plus neutral "needs review" flags. No Present/Absent/Late/Early/worked
hours — those require an approved attendance policy (Phase 3).
``PunchState`` is never interpreted.

Identity (identity redesign): every code-day is resolved through the
administrator-verified mapping layer (``identity_resolution``). Only
identified code-days become rows, and they are merged per **BambooHR
employee and day** — an employee with several ZKBioTime IDs is one row, one
headcount. Unmapped / conflicting code-days never appear here; they are
visible only in Identity Management. BambooHR Employee Number equality is
never used.
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import date

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import IdentityClass, ReviewFlag
from app.repositories.attendance_repository import AttendanceRepository
from app.services.identity_resolution import MappingIndex, ResolvedIdentity, legacy_identity_class
from app.services.time_derivation import site_today, to_site_local
from app.services.workforce_directory import DirectorySnapshot

_IDENTITY_FLAG = {
    IdentityClass.MATCHED_INACTIVE.value: ReviewFlag.INACTIVE_EMPLOYEE_ACTIVITY,
    IdentityClass.MATCHED_BEFORE_HIRE.value: ReviewFlag.BEFORE_HIRE_ACTIVITY,
}


def identity_fields(r: ResolvedIdentity, codes: Collection[str] | None = None) -> dict:
    """The employee identity carried by every viewer row (legacy keys + additive new-contract keys)."""
    return {
        "bamboohr_id": r.bamboohr_id, "employee_number": r.employee_number, "employee_name": r.employee_name,
        "department": r.department, "employment_status": r.employment_status, "has_photo": r.has_photo,
        "mapping_status": r.mapping_status.value,
        "zk_emp_codes": sorted(codes) if codes is not None else [r.emp_code],
    }


def daily_activity(
    db: Session, *, allowed_site_ids: Collection[str], site_id: str, site_time_zone: str | None,
    date_from: date, date_to: date, directory: DirectorySnapshot, today: date | None = None,
    emp_codes: Collection[str] | None = None, bamboohr_ids: Collection[str] | None = None,
    index: MappingIndex | None = None,
) -> list[dict]:
    """Identified employee-day rows. ``emp_codes`` restricts the ZKBioTime IDs
    considered; ``bamboohr_ids`` restricts the employees."""
    settings = get_settings()
    index = index or MappingIndex.load(db, allowed_site_ids=allowed_site_ids, directory=directory)
    windows = index.windows(site_id, date_from, date_to, codes=emp_codes, bamboohr_ids=bamboohr_ids)
    if not windows or site_id not in allowed_site_ids:
        return []
    codes = {c for c, _lo, _hi in windows}
    repo = AttendanceRepository(db)

    resolved: dict[tuple[date, str], ResolvedIdentity] = {}
    acc: dict[tuple[str, date], dict] = {}
    for _site, local_date, code, count, first, last, _terms, inconsistent in repo.daily_groups(
        allowed_site_ids=allowed_site_ids, site_id=site_id, date_from=date_from, date_to=date_to, emp_codes=codes,
    ):
        r = index.resolve(site_id, code, local_date)
        if not r.identified or (bamboohr_ids is not None and r.bamboohr_id not in bamboohr_ids):
            continue
        resolved[(local_date, code)] = r
        key = (r.bamboohr_id, local_date)
        a = acc.get(key)
        if a is None:
            acc[key] = {"identity": r, "codes": {code}, "count": count, "first": first, "last": last,
                        "inconsistent": inconsistent or 0, "punches": [], "terminals": set()}
        else:
            a["codes"].add(code)
            a["count"] += count
            a["first"], a["last"] = min(a["first"], first), max(a["last"], last)
            a["inconsistent"] += inconsistent or 0

    for local_date, code, utc, terminal_sn in repo.punch_rows(
        allowed_site_ids=allowed_site_ids, site_id=site_id, date_from=date_from, date_to=date_to, emp_codes=codes,
    ):
        r = resolved.get((local_date, code))
        if r is None:
            continue
        a = acc[(r.bamboohr_id, local_date)]
        a["punches"].append(utc)
        if terminal_sn:
            a["terminals"].add(terminal_sn)

    today = today or site_today(site_time_zone)
    out = []
    for (_bid, local_date), a in sorted(acc.items(), key=lambda kv: (kv[0][1], min(kv[1]["codes"]))):
        r: ResolvedIdentity = a["identity"]
        punches = sorted(a["punches"])
        flags: list[str] = []
        if a["count"] == 1 and local_date < today:
            flags.append(ReviewFlag.SINGLE_PUNCH.value)
        if a["count"] >= settings.high_punch_count_threshold:
            flags.append(ReviewFlag.HIGH_PUNCH_COUNT.value)
        if any((b - p).total_seconds() <= settings.duplicate_tap_seconds for p, b in zip(punches, punches[1:],
                                                                                         strict=False)):
            flags.append(ReviewFlag.POSSIBLE_DUPLICATE_TAP.value)
        legacy = legacy_identity_class(r, local_date, local_date)
        if legacy in _IDENTITY_FLAG:
            flags.append(_IDENTITY_FLAG[legacy].value)
        if a["inconsistent"]:
            flags.append(ReviewFlag.TZ_INCONSISTENT.value)
        first, last = a["first"], a["last"]
        out.append({
            "site_id": site_id, "local_date": local_date.isoformat(),
            # Legacy row key: the employee's lowest ZKBioTime ID that day (stable, verified).
            "emp_code": min(a["codes"]),
            **identity_fields(r, a["codes"]),
            "first_activity_utc": first.isoformat(), "latest_activity_utc": last.isoformat(),
            "first_activity_local": to_site_local(first, site_time_zone),
            "latest_activity_local": to_site_local(last, site_time_zone),
            "punch_count": a["count"], "span_minutes": int((last - first).total_seconds() // 60),
            "terminals": len(a["terminals"]), "identity_class": legacy, "flags": flags,
        })
    return out
