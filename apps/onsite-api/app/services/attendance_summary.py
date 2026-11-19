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
from datetime import date, datetime

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


def recorded_span(first_utc: datetime | None, last_utc: datetime | None, count: int) -> int | None:
    """Recorded Span in whole minutes: last minus first recorded fingerprint of
    an identity-day. ``None`` (unavailable — never 0) for a single fingerprint.
    The ONE calculation used by Today, the Daily summary, Activity details and
    every export. A measured interval between observations at an entry-side
    reader — not a confirmed exit, presence or working hours."""
    if count < 2 or first_utc is None or last_utc is None:
        return None
    return int((last_utc - first_utc).total_seconds() // 60)


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
            # Legacy key (0 for a single fingerprint, kept for the running contract);
            # ``recorded_span_minutes`` is the v0.9 value (None = unavailable).
            "punch_count": a["count"], "span_minutes": int((last - first).total_seconds() // 60),
            "recorded_span_minutes": recorded_span(first, last, a["count"]),
            "terminals": len(a["terminals"]), "identity_class": legacy, "flags": flags,
        })
    return out


# --- v0.9: daily fingerprint activity for EVERY identity -----------------------
# Identity kinds of an identity-day. PERSON = a verified BambooHR employee (all
# of their ZKBioTime IDs valid that day, merged); CODE = a raw ZKBioTime ID
# whose day is UNMAPPED or CONFLICT (never merged, never attributed).
PERSON, CODE = "PERSON", "CODE"
VERIFIED, UNMAPPED, CONFLICT = "VERIFIED", "UNMAPPED", "CONFLICT"


def state_of(r: ResolvedIdentity) -> str:
    if r.identified:
        return VERIFIED
    return CONFLICT if r.mapping_status.value == "MAPPING_CONFLICT" else UNMAPPED


def identity_key_for(r: ResolvedIdentity, code: str) -> str:
    """Stable review/grouping key: ``P:<bamboohr_id>`` or ``C:<zk_emp_code>``."""
    return f"P:{r.bamboohr_id}" if r.identified else f"C:{code}"


def daily_identity_rows(
    db: Session, *, allowed_site_ids: Collection[str], site_id: str, site_time_zone: str | None,
    date_from: date, date_to: date, index: MappingIndex,
) -> list[dict]:
    """One row per identity-day over ALL recorded fingerprints of the site and
    range (complete days; filtering happens afterwards). Every code-day is
    classified by the mapping valid on its own day. Verified code-days merge
    per (BambooHR employee, day); unmapped and conflict code-days stay per
    (raw ZKBioTime ID, day) and never carry a person. Σ punch_count per state
    equals the Activity summary for the same range."""
    if site_id not in allowed_site_ids:
        return []
    repo = AttendanceRepository(db)
    acc: dict[tuple[str, date], dict] = {}
    for _site, local_date, code, count, first, last, _terms, inconsistent in repo.daily_groups(
        allowed_site_ids=allowed_site_ids, site_id=site_id, date_from=date_from, date_to=date_to,
    ):
        r = index.resolve(site_id, code, local_date)
        key = (identity_key_for(r, code), local_date)
        a = acc.get(key)
        if a is None:
            acc[key] = {"identity": r, "state": state_of(r), "codes": {code}, "count": count, "first": first,
                        "last": last, "inconsistent": inconsistent or 0}
        else:
            a["codes"].add(code)
            a["count"] += count
            a["first"], a["last"] = min(a["first"], first), max(a["last"], last)
            a["inconsistent"] += inconsistent or 0
    terminals: dict[tuple[date, str], set[str]] = {}
    for d, code, alias in repo.terminals_by_day(allowed_site_ids=allowed_site_ids, site_id=site_id,
                                                date_from=date_from, date_to=date_to):
        if alias:
            terminals.setdefault((d, code), set()).add(alias)

    out = []
    for (ikey, local_date), a in acc.items():
        r: ResolvedIdentity = a["identity"]
        verified = a["state"] == VERIFIED
        first, last, count = a["first"], a["last"], a["count"]
        names: set[str] = set()
        for c in a["codes"]:
            names |= terminals.get((local_date, c), set())
        person = identity_fields(r, a["codes"]) if verified else {
            "bamboohr_id": None, "employee_number": None, "employee_name": None, "department": None,
            "employment_status": None, "has_photo": False, "mapping_status": r.mapping_status.value,
            "zk_emp_codes": sorted(a["codes"]),
        }
        out.append({
            "site_id": site_id, "local_date": local_date.isoformat(), "time_zone": site_time_zone,
            "identity_key": ikey, "identity_kind": PERSON if verified else CODE, "mapping_state": a["state"],
            "emp_code": min(a["codes"]), **person,
            "first_fingerprint_utc": first.isoformat(), "last_fingerprint_utc": last.isoformat(),
            "first_fingerprint_local": to_site_local(first, site_time_zone),
            "last_fingerprint_local": to_site_local(last, site_time_zone),
            "punch_count": count, "recorded_span_minutes": recorded_span(first, last, count),
            "single": count == 1, "terminal_names": sorted(names), "tz_inconsistent": a["inconsistent"],
        })
    out.sort(key=lambda row: (row["local_date"], row["first_fingerprint_utc"], row["identity_key"]))
    return out
