"""Backward-compatible API contract (expand/contract transition, review §I.2).

While ``ONSITE_LEGACY_CONTRACT`` is on, the pre-redesign routes and response
shapes keep working for the running onsite-web — but every value is derived
from VERIFIED mappings only:

- code-addressed routes (``/employees/{emp_code}``, ``/employees/{emp_code}/photo``)
  resolve the ID through its verified owner, or 404;
- the legacy ``identity_class`` vocabulary is computed from the mapped
  employee (``MATCHED_ACTIVE/INACTIVE/BEFORE_HIRE``); viewer endpoints never
  emit ``UNMATCHED``/``AMBIGUOUS`` because unmapped code-days are not emitted;
- the admin Identity Match report keeps its shape; ``matches`` holds the
  verified owner (or nothing) — never Employee Number equality.

Switched off (and this module deleted) in API N+2 once onsite-web N+1 has run
cleanly; numeric matching is never a fallback.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import IdentityClass
from app.repositories.attendance_repository import AttendanceRepository
from app.repositories.site_repository import SiteRepository
from app.services.identity_resolution import MappingIndex, legacy_identity_class
from app.services.time_derivation import site_today
from app.services.workforce_directory import DirectorySnapshot


def require_legacy_contract() -> None:
    if not get_settings().onsite_legacy_contract:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")


def employee_owning_code_today(db: Session, allowed_site_ids: Collection[str], code: str) -> str | None:
    """The single verified owner of ``code`` today (site-local) across the sites
    in scope; None when unverified or ambiguous across sites."""
    from app.services import workforce_directory

    index = MappingIndex.load(db, allowed_site_ids=allowed_site_ids, directory=workforce_directory.load())
    tzs = SiteRepository(db).time_zones(list(allowed_site_ids))
    owners = set()
    for site in allowed_site_ids:
        r = index.resolve(site, code, site_today(tzs.get(site)))
        if r.identified:
            owners.add(r.bamboohr_id)
    return owners.pop() if len(owners) == 1 else None


CSV_COLUMNS = ["emp_code", "identity_class", "event_count", "first_seen", "last_seen",
               "match_count", "bamboohr_ids", "employment_status"]


def identity_match_report(db: Session, allowed_site_ids: Collection[str], directory: DirectorySnapshot) -> dict:
    """LEGACY admin report shape, computed from verified mappings. A code is
    'matched' only through its verified owner on its last day of activity;
    otherwise UNMATCHED (admin-only view). AMBIGUOUS is never produced."""
    index = MappingIndex.load(db, allowed_site_ids=allowed_site_ids, directory=directory)
    repo = AttendanceRepository(db)
    activity = repo.emp_code_activity(allowed_site_ids=allowed_site_ids)
    rows = []
    for code, count, first, last in activity:
        owner = None
        for site in sorted(allowed_site_ids):
            r = index.resolve(site, code, last)
            if r.identified:
                owner = r
                break
        cls = (legacy_identity_class(owner, first, last) if owner else IdentityClass.UNMATCHED.value) \
            if directory.available else None
        matches = []
        if owner is not None:
            matches = [{"bamboohr_id": owner.bamboohr_id, "display_name": owner.employee_name,
                        "employment_status": owner.employment_status, "department": owner.department,
                        "has_photo": owner.has_photo}]
        rows.append({"emp_code": code, "identity_class": cls, "event_count": count, "first_seen": first.isoformat(),
                     "last_seen": last.isoformat(), "matches": matches})
    if not directory.available:
        return {"directory_available": False, "summary": {"attendance_emp_codes": len(activity)}, "rows": rows}
    numbers = [e.get("employee_number") for e in directory.entries]
    present = [n for n in numbers if n is not None and str(n).strip()]
    counts = Counter(present)
    mapped_people = {m["bamboohr_id"] for r in rows for m in r["matches"]}
    by_class = Counter(r["identity_class"] for r in rows)
    return {
        "directory_available": True,
        "summary": {
            "attendance_emp_codes": len(activity),
            **{cls.value: by_class.get(cls.value, 0) for cls in IdentityClass},
            "directory_total": len(directory.entries),
            "directory_blank_employee_numbers": len(numbers) - len(present),
            "directory_duplicate_employee_numbers": sum(1 for v in counts.values() if v > 1),
            # Directory employees with no verified attendance identity.
            "directory_entries_without_attendance": sum(
                1 for e in directory.entries if str(e.get("bamboohr_id")) not in mapped_people),
        },
        "rows": rows,
    }


def csv_rows(report: dict) -> list[list]:
    return [[r["emp_code"], r["identity_class"] or "", r["event_count"], r["first_seen"], r["last_seen"],
             len(r["matches"]), ";".join(m["bamboohr_id"] for m in r["matches"]),
             ";".join(m["employment_status"] or "" for m in r["matches"])] for r in report["rows"]]
