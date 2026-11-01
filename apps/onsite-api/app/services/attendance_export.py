"""Diji On-site Excel exports — the same filter model as the dashboard views,
re-applied server-side inside the caller's enabled-site scope.

Neutral facts only (no Present/Absent/Late/Early/worked hours). Exports never
carry database ids, hashes, epochs or other technical mirror fields. Size is
capped so an accidental "everything" export fails fast with a clear message
instead of building a huge workbook."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, fields
from datetime import date, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.constants import ReviewFlag
from app.repositories.attendance_repository import AttendanceRepository
from app.services import dashboard_service as svc
from app.services.attendance_summary import daily_activity
from app.services.excel_report import Column, Sheet
from app.services.workforce_directory import DirectorySnapshot

MAX_EXPORT_DAY_ROWS = 20_000
MAX_EXPORT_EVENTS = 50_000

FLAG_LABEL = {
    "SINGLE_PUNCH": "Single activity", "POSSIBLE_DUPLICATE_TAP": "Possible duplicate tap",
    "UNMATCHED_CODE": "Unmatched code", "AMBIGUOUS_CODE": "Ambiguous code",
    "INACTIVE_EMPLOYEE_ACTIVITY": "Inactive employee activity", "BEFORE_HIRE_ACTIVITY": "Before-hire activity",
    "TZ_INCONSISTENT": "Time zone inconsistent", "HIGH_PUNCH_COUNT": "High activity count",
}
IDENTITY_LABEL = {
    "MATCHED_ACTIVE": "Matched (active)", "MATCHED_INACTIVE": "Matched (inactive)",
    "MATCHED_BEFORE_HIRE": "Matched (before hire date)", "AMBIGUOUS": "Ambiguous Employee Number",
    "UNMATCHED": "No matching Employee Number",
}
_REVIEW_LABEL = {"needs_review": "Needs review", "no_flags": "No review flags", **FLAG_LABEL}


@dataclass
class ExportFilters:
    q: str | None = None
    emp_code: str | None = None
    department: str | None = None
    identity_class: str | None = None
    employment_status: str | None = None
    review: str | None = None
    terminal: str | None = None


def too_large(count: int, limit: int) -> HTTPException:
    return HTTPException(
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        f"This export would contain {count:,} rows, above the limit of {limit:,}. "
        "Narrow the date range or add filters and try again.",
    )


def _flags_text(flags: list[str]) -> str:
    return ", ".join(FLAG_LABEL.get(f, f) for f in flags)


def _local(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _time(value: str | None):
    dt = _local(value)
    return dt.time().replace(microsecond=0) if dt else None


# --- data selection ----------------------------------------------------------


def day_rows(db: Session, allowed, site_id: str, tz: str | None, start: date, end: date,
             directory: DirectorySnapshot, f: ExportFilters) -> list[dict]:
    """Employee-day rows matching every filter, enriched from the Workforce
    Directory (display/filter only — identity stays exact EmpCode equality)."""
    ident = svc.Identity(directory)
    rows = daily_activity(db, allowed_site_ids=allowed, site_id=site_id, site_time_zone=tz, date_from=start,
                          date_to=end, directory=directory, emp_codes=[f.emp_code] if f.emp_code else None)
    out = []
    for r in rows:
        day = date.fromisoformat(r["local_date"])
        d = ident.describe(r["emp_code"], day, day)
        row = {**r, "employee_name": d["employee_name"], "department": d["department"],
               "employment_status": d["employment_status"]}
        if svc._match(row, q=f.q, emp_code=f.emp_code, department=f.department, identity_class=f.identity_class,
                      employment_status=f.employment_status) and svc._review_hit(row, f.review):
            out.append(row)
    if len(out) > MAX_EXPORT_DAY_ROWS:
        raise too_large(len(out), MAX_EXPORT_DAY_ROWS)
    svc._with_terminals(db, allowed, site_id, start, end, out, {r["emp_code"] for r in out} or None)
    if f.terminal:
        out = [r for r in out if f.terminal in r["terminal_names"]]
    out.sort(key=lambda r: (r["local_date"], r.get("employee_name") or "~", r["emp_code"]))
    return out


def event_rows(db: Session, allowed, site_id: str, start: date, end: date, days: list[dict],
               terminal: str | None) -> list[dict]:
    """Raw events belonging to the selected employee-days, oldest first."""
    if not days:
        return []
    flags = {(r["local_date"], r["emp_code"]): r for r in days}
    total, events = AttendanceRepository(db).events_page(
        allowed_site_ids=allowed, site_id=site_id, date_from=start, date_to=end,
        emp_codes={r["emp_code"] for r in days}, terminal=terminal, offset=0, limit=MAX_EXPORT_EVENTS + 1,
    )
    if total > MAX_EXPORT_EVENTS:
        raise too_large(total, MAX_EXPORT_EVENTS)
    out = []
    for e in reversed(events):
        day = flags.get((e.site_local_date.isoformat(), e.emp_code))
        if day is not None:
            out.append({"event": e, "day": day})
    return out


# --- sheets ------------------------------------------------------------------

_ATTENDANCE_COLUMNS = [
    Column("Date", 12, "date"), Column("Employee Number", 16), Column("Employee Name", 26),
    Column("Department", 20), Column("Employment Status", 14), Column("First Activity", 13, "time"),
    Column("Latest Activity", 13, "time"), Column("Punch Count", 12, "int"),
    Column("Activity Span (minutes)", 14, "int"), Column("Terminal(s)", 20, wrap=True),
    Column("Identity Classification", 24), Column("Review Flags", 32, wrap=True),
]


def attendance_sheet(days: list[dict], *, title: str = "Attendance Report", with_reasons: bool = False) -> Sheet:
    cols = list(_ATTENDANCE_COLUMNS)
    if with_reasons:
        cols.append(Column("Review Reasons", 60, wrap=True))
    rows = []
    for r in days:
        row = [date.fromisoformat(r["local_date"]), r["emp_code"], r.get("employee_name"), r.get("department"),
               r.get("employment_status"), _time(r["first_activity_local"]), _time(r["latest_activity_local"]),
               r["punch_count"], r["span_minutes"], ", ".join(r.get("terminal_names") or []),
               IDENTITY_LABEL.get(r.get("identity_class") or "", "Directory unavailable"), _flags_text(r["flags"])]
        if with_reasons:
            row.append(" ".join(svc._FLAG_REASON[f] for f in r["flags"]))
        rows.append(row)
    return Sheet(title, cols, rows)


def event_sheet(events: list[dict]) -> Sheet:
    cols = [Column("Local Date", 12, "date"), Column("Local Time", 11, "time"), Column("Employee Number", 16),
            Column("Employee Name", 26), Column("Department", 20), Column("Terminal", 18),
            Column("Verify Type", 11), Column("Identity Classification", 24), Column("Review Flags", 32, wrap=True)]
    rows = []
    for item in events:
        e, day = item["event"], item["day"]
        rows.append([e.site_local_date, _time(e.punch_time_local), e.emp_code, day.get("employee_name"),
                     day.get("department"), e.terminal_alias, e.verify_type,
                     IDENTITY_LABEL.get(day.get("identity_class") or "", "Directory unavailable"),
                     _flags_text(day["flags"])])
    return Sheet("Event Detail", cols, rows)


def summary_sheet(days: list[dict], start: date, end: date) -> Sheet:
    counts = Counter(f for r in days for f in r["flags"])
    flagged = {r["emp_code"] for r in days if r["flags"]}
    unmatched = {r["emp_code"] for r in days if ReviewFlag.UNMATCHED_CODE.value in r["flags"]}
    rows: list[list] = [
        ["Date range", f"{start.isoformat()} to {end.isoformat()}"],
        ["Employees with activity", len({r["emp_code"] for r in days})],
        ["Employee-days with activity", len(days)],
        ["Attendance events", sum(r["punch_count"] for r in days)],
        ["Employees needing review", len(flagged)],
        ["Single-activity days", counts.get(ReviewFlag.SINGLE_PUNCH.value, 0)],
        ["Unmatched codes", len(unmatched)],
    ]
    rows += [[f"Review flag: {FLAG_LABEL[f]}", counts.get(f, 0)] for f in svc.REVIEW_FLAGS]
    return Sheet("Summary", [Column("Measure", 36), Column("Value", 24)], rows)


# --- metadata ------------------------------------------------------------------


def filter_summary(site_name: str, date_label: str, f: ExportFilters) -> list[tuple[str, str]]:
    labels = {"q": "Employee search", "emp_code": "Employee Number", "department": "Department",
              "identity_class": "Identity classification", "employment_status": "Employment status",
              "review": "Review / exception type", "terminal": "Terminal"}
    out = [("Site", site_name), ("Date range" if " to " in date_label else "Date", date_label)]
    for fld in fields(ExportFilters):
        value = getattr(f, fld.name)
        if fld.name == "identity_class" and value:
            value = IDENTITY_LABEL.get(value, value)
        if fld.name == "review" and value:
            value = _REVIEW_LABEL.get(value, value)
        out.append((labels[fld.name], value or "All"))
    return out


def site_name(db: Session, allowed, site_id: str) -> str:
    return next((s["name"] for s in svc._sites(db, allowed) if s["site_id"] == site_id), site_id)


def filename(report: str, start: date, end: date, *parts: str | None) -> str:
    def clean(v: str) -> str:
        return re.sub(r"[^A-Za-z0-9]+", "-", v).strip("-")[:40]
    span = start.isoformat() if start == end else f"{start.isoformat()}_to_{end.isoformat()}"
    bits = ["Diji-Onsite", clean(report), *[clean(p) for p in parts if p and clean(p)], span]
    return "_".join(bits) + ".xlsx"

