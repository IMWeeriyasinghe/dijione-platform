"""EmpCode -> Employee Number identity matching (deterministic, auditable).

Rule: ``AttendanceEvents.EmpCode == WorkforceDirectory.employee_number`` by
exact, case-sensitive string equality. Never trim, strip leading zeros,
cast to a number, fuzzy-match or match by name. Unmatched and ambiguous
codes are reported, never hidden or auto-resolved.
"""

from __future__ import annotations

from collections import Counter
from datetime import date

from app.core.constants import IdentityClass
from app.services.workforce_directory import DirectorySnapshot


def _parse(d: str | None) -> date | None:
    return date.fromisoformat(d) if d else None


def classify(matches: list[dict], first_seen: date, last_seen: date) -> IdentityClass:
    if not matches:
        return IdentityClass.UNMATCHED
    if len(matches) > 1:
        return IdentityClass.AMBIGUOUS
    e = matches[0]
    term = _parse(e.get("termination_date"))
    if e.get("employment_status") != "Active" or (term is not None and last_seen > term):
        return IdentityClass.MATCHED_INACTIVE
    hire = _parse(e.get("hire_date"))
    if hire is not None and first_seen < hire:
        return IdentityClass.MATCHED_BEFORE_HIRE
    return IdentityClass.MATCHED_ACTIVE


def build_report(activity: list[tuple[str, int, date, date]], directory: DirectorySnapshot) -> dict:
    """``activity`` = (emp_code, event_count, first_local_date, last_local_date)."""
    if not directory.available:
        return {
            "directory_available": False,
            "summary": {"attendance_emp_codes": len(activity)},
            "rows": [
                {"emp_code": c, "identity_class": None, "event_count": n,
                 "first_seen": f.isoformat(), "last_seen": la.isoformat(), "matches": []}
                for c, n, f, la in activity
            ],
        }

    index = directory.by_employee_number()
    rows = []
    for code, count, first, last in activity:
        matches = index.get(code, [])
        rows.append({
            "emp_code": code,
            "identity_class": classify(matches, first, last).value,
            "event_count": count,
            "first_seen": first.isoformat(),
            "last_seen": last.isoformat(),
            "matches": [
                {"bamboohr_id": m["bamboohr_id"], "display_name": m.get("display_name"),
                 "employment_status": m.get("employment_status"), "department": m.get("department")}
                for m in matches
            ],
        })

    numbers = [e.get("employee_number") for e in directory.entries]
    present = [n for n in numbers if n is not None and str(n).strip()]
    counts = Counter(present)
    attended = {c for c, *_ in activity}
    by_class = Counter(r["identity_class"] for r in rows)
    return {
        "directory_available": True,
        "summary": {
            "attendance_emp_codes": len(activity),
            **{cls.value: by_class.get(cls.value, 0) for cls in IdentityClass},
            "directory_total": len(directory.entries),
            "directory_blank_employee_numbers": len(numbers) - len(present),
            "directory_duplicate_employee_numbers": sum(1 for v in counts.values() if v > 1),
            "directory_entries_without_attendance": sum(
                1 for e in directory.entries
                if e.get("employee_number") is None or e.get("employee_number") not in attended
            ),
        },
        "rows": rows,
    }


CSV_COLUMNS = ["emp_code", "identity_class", "event_count", "first_seen", "last_seen",
               "match_count", "bamboohr_ids", "employment_status"]


def csv_rows(report: dict) -> list[list]:
    out = []
    for r in report["rows"]:
        out.append([
            r["emp_code"], r["identity_class"] or "", r["event_count"], r["first_seen"], r["last_seen"],
            len(r["matches"]), ";".join(m["bamboohr_id"] for m in r["matches"]),
            ";".join(m["employment_status"] or "" for m in r["matches"]),
        ])
    return out
