"""Diji On-site Excel exports — the same filter model as the dashboard views,
re-applied server-side inside the caller's enabled-site scope.

Neutral facts only (no Present/Absent/Late/Early/worked hours). Exports never
carry database ids, hashes, epochs or other technical mirror fields. Size is
capped so an accidental "everything" export fails fast with a clear message
instead of building a huge workbook."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, fields, replace
from datetime import UTC, date, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.constants import ReviewFlag
from app.repositories.attendance_repository import AttendanceRepository
from app.services import dashboard_service as svc
from app.services.attendance_summary import daily_activity
from app.services.excel_report import REVIEW_GROUP, Column, Sheet
from app.services.identity_resolution import MappingIndex
from app.services.workforce_directory import DirectorySnapshot

MAX_EXPORT_DAY_ROWS = 20_000
MAX_EXPORT_EVENTS = 50_000

FLAG_LABEL = {
    "SINGLE_PUNCH": "Single Recorded Fingerprint", "POSSIBLE_DUPLICATE_TAP": "Possible duplicate tap",
    "UNMATCHED_CODE": "Unmatched code", "AMBIGUOUS_CODE": "Ambiguous code",
    "INACTIVE_EMPLOYEE_ACTIVITY": "Inactive team member activity", "BEFORE_HIRE_ACTIVITY": "Before-hire activity",
    "TZ_INCONSISTENT": "Time zone inconsistent", "HIGH_PUNCH_COUNT": "High activity count",
}
IDENTITY_LABEL = {  # legacy filter vocabulary (derived from the verified employee)
    "MATCHED_ACTIVE": "Verified (active)", "MATCHED_INACTIVE": "Verified (inactive)",
    "MATCHED_BEFORE_HIRE": "Verified (before hire date)", "AMBIGUOUS": "Ambiguous", "UNMATCHED": "Unmapped",
}
MAPPING_LABEL = {
    "MAPPED": "Verified", "MAPPED_DIRECTORY_MISSING": "Verified (team member not in directory)",
    "DIRECTORY_UNAVAILABLE": "Verified (directory unavailable)",
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
    """Verified employee-day rows matching every filter. Unmapped attendance is
    never exported here (it is counted in the summary and handled in Identity
    Management)."""
    rows = daily_activity(db, allowed_site_ids=allowed, site_id=site_id, site_time_zone=tz, date_from=start,
                          date_to=end, directory=directory)
    out = [r for r in rows if svc._match(r, q=f.q, emp_code=f.emp_code, department=f.department,
                                         identity_class=f.identity_class, employment_status=f.employment_status)
           and svc._review_hit(r, f.review)]
    if len(out) > MAX_EXPORT_DAY_ROWS:
        raise too_large(len(out), MAX_EXPORT_DAY_ROWS)
    svc._with_terminals(db, allowed, site_id, start, end, out, True)
    if f.terminal:
        out = [r for r in out if f.terminal in r["terminal_names"]]
    out.sort(key=lambda r: (r["local_date"], r.get("employee_name") or "~", r["emp_code"]))
    return out


def unmapped_punches(db: Session, allowed, site_id: str, start: date, end: date, directory: DirectorySnapshot) -> int:
    return svc.operational(db, allowed, site_id, start, end,
                           MappingIndex.load(db, allowed_site_ids=allowed, directory=directory))["unmapped_punches"]


def _by_code_day(days: list[dict]) -> dict[tuple[str, str], dict]:
    return {(r["local_date"], c): r for r in days for c in r["zk_emp_codes"]}


def event_rows(db: Session, allowed, site_id: str, start: date, end: date, days: list[dict],
               terminal: str | None) -> list[dict]:
    """Raw events belonging to the selected verified employee-days, oldest first."""
    if not days:
        return []
    windows = [(c, date.fromisoformat(r["local_date"]), date.fromisoformat(r["local_date"]))
               for r in days for c in r["zk_emp_codes"]]
    total, events = AttendanceRepository(db).events_page(
        allowed_site_ids=allowed, site_id=site_id, date_from=start, date_to=end, code_windows=windows,
        terminal=terminal, offset=0, limit=MAX_EXPORT_EVENTS + 1,
    )
    if total > MAX_EXPORT_EVENTS:
        raise too_large(total, MAX_EXPORT_EVENTS)
    return pair_events(events, _by_code_day(days))


def pair_events(events, by_code_day: dict) -> list[dict]:
    """Attach each event's verified employee-day row (keyed by date + ZKBioTime ID); oldest first."""
    out = []
    for e in reversed(events):
        day = by_code_day.get((e.site_local_date.isoformat(), e.emp_code))
        if day is not None:
            out.append({"event": e, "day": day})
    return out


# --- sheets ------------------------------------------------------------------

# Entry-only fingerprint terminology (v0.9): the site records fingerprints at an
# entry-side reader; the final fingerprint is never an exit. Recorded Span is
# blank (unavailable) for a single fingerprint — never 0.
_ATTENDANCE_COLUMNS = [
    Column("Date", 12, "date"), Column("Team Member Name", 26), Column("BHR ID", 14),
    Column("EMP Number", 16), Column("ZKBioTime ID(s)", 16), Column("Department", 20),
    Column("Employment Status", 14), Column("First Recorded Fingerprint", 13, "time"),
    Column("Last Recorded Fingerprint", 13, "time"),
    Column("Punch Count", 12, "int"), Column("Recorded Span (minutes)", 14, "int"),
    Column("Terminal(s)", 20, wrap=True), Column("Mapping Status", 22), Column("Review Flags", 32, wrap=True),
]

# --- administrative review columns (Decision 5) -----------------------------
REVIEW_NOTE = "Reviewed declarations — not biometric records. A resolved case is not a verified duration."
STATUS_LABEL = {"OPEN": "Under review", "SUBMITTED": "Justification submitted",
                "RESOLVED": "Resolved — duration not verified", "REOPENED": "Reopened"}
TYPE_LABEL = {"SINGLE_RECORDED_FINGERPRINT": "Single Recorded Fingerprint",
              "DEPARTURE_TIME_QUERY": "Departure time query", "DISPUTED_SPAN": "Disputed Recorded Span",
              "DEVICE_ISSUE": "Device issue", "IDENTITY_ISSUE": "Identity issue", "OTHER": "Other"}
REASON_LABEL = {"FORGOT_TO_RECORD": "Fingerprint not recorded", "DEVICE_FAULT": "Device fault",
                "ASSIGNED_OFF_SITE": "Assigned off-site", "APPROVED_LEAVE_OR_DUTY": "Approved leave or duty",
                "OTHER": "Other"}
OUTCOME_LABEL = {"JUSTIFIED": "Justified", "NO_FURTHER_ACTION": "No further action",
                 "NOT_JUSTIFIED": "Not justified"}
SOURCE_LABEL = {"TEAM_MEMBER_STATEMENT": "Team member statement", "MANAGER_CONFIRMATION": "Manager confirmation",
                "SECURITY_OR_VISITOR_LOG": "Security or visitor log", "OTHER": "Other"}
REVIEW_COLUMNS = [
    Column("Classification", 26, group=REVIEW_GROUP),
    Column("Review Status", 24, group=REVIEW_GROUP), Column("Outcome", 16, group=REVIEW_GROUP),
    Column("Justification", 22, group=REVIEW_GROUP),
    Column("Explanation", 40, wrap=True, group=REVIEW_GROUP),
    Column("Declared Departure (declaration)", 16, "time", group=REVIEW_GROUP),
    Column("Declaration Source", 20, group=REVIEW_GROUP),
    Column("Estimated Interval (minutes, reviewed estimate)", 16, "int", group=REVIEW_GROUP),
    Column("Estimate Basis", 48, wrap=True, group=REVIEW_GROUP),
    Column("Duration Verified", 12, group=REVIEW_GROUP),
    Column("Reviewer", 20, group=REVIEW_GROUP),
    Column("Reviewed At (UTC)", 18, "datetime", group=REVIEW_GROUP),
    Column("Needs Reassessment", 22, wrap=True, group=REVIEW_GROUP),
]
_REASSESS_LABEL = {"FINGERPRINTS_CHANGED": "Recorded fingerprints changed",
                   "IDENTITY_CHANGED": "Identity mapping changed",
                   "ESTIMATE_BASIS_INVALID": "Fingerprint after declared departure"}


def review_cells(r: dict, *, classification: str | None) -> list:
    """The Administrative review group of one identity-day row (blank when no case)."""
    rv = r.get("review")
    if rv is None:
        return [classification, "Not reviewed", None, None, None, None, None, None, None, "No", None, None, None]
    reviewed = datetime.fromisoformat(rv["reviewed_at"]).astimezone(UTC).replace(tzinfo=None) \
        if rv.get("reviewed_at") else None
    return [
        TYPE_LABEL.get(rv["exception_type"], rv["exception_type"]), STATUS_LABEL.get(rv["status"], rv["status"]),
        OUTCOME_LABEL.get(rv.get("outcome") or "", None), REASON_LABEL.get(rv.get("justification_reason") or "", None),
        rv.get("explanation"), _time(rv.get("declared_departure_local")),
        SOURCE_LABEL.get(rv.get("declaration_source") or "", None), rv.get("estimated_minutes"),
        rv.get("estimate_basis"), "No", rv.get("reviewer"), reviewed,
        ", ".join(_REASSESS_LABEL.get(x, x) for x in rv.get("reassess_reasons") or []) or None,
    ]


def _mapping_label(r: dict) -> str:
    return MAPPING_LABEL.get(r.get("mapping_status") or "", r.get("mapping_status") or "")


def attendance_sheet(days: list[dict], *, title: str = "Attendance Report", with_reasons: bool = False,
                     with_review: bool = False) -> Sheet:
    cols = list(_ATTENDANCE_COLUMNS)
    if with_reasons:
        cols.append(Column("Review Reasons", 60, wrap=True))
    if with_review:  # two labelled groups: recorded evidence | administrative review
        cols = [replace(c, group=EVIDENCE_GROUP) for c in cols] + REVIEW_COLUMNS
    rows = []
    for r in days:
        row = [date.fromisoformat(r["local_date"]), r.get("employee_name"), r.get("bamboohr_id"),
               r.get("employee_number"), ", ".join(r.get("zk_emp_codes") or []), r.get("department"),
               r.get("employment_status"), _time(r["first_activity_local"]), _time(r["latest_activity_local"]),
               r["punch_count"], r.get("recorded_span_minutes"), ", ".join(r.get("terminal_names") or []),
               _mapping_label(r), _flags_text(r["flags"])]
        if with_reasons:
            row.append(" ".join(svc._FLAG_REASON[f] for f in r["flags"]))
        if with_review:
            row += review_cells(r, classification=_flags_text(r["flags"]) or None)
        rows.append(row)
    return Sheet(title, cols, rows)


def event_sheet(events: list[dict]) -> Sheet:
    cols = [Column("Local Date", 12, "date"), Column("Local Time", 11, "time"), Column("ZKBioTime ID", 14),
            Column("Team Member Name", 26), Column("BHR ID", 14), Column("EMP Number", 16),
            Column("Department", 20), Column("Terminal", 18), Column("Verify Type", 11), Column("Mapping Status", 22),
            Column("Review Flags", 32, wrap=True)]
    rows = []
    for item in events:
        e, day = item["event"], item["day"]
        rows.append([e.site_local_date, _time(e.punch_time_local), e.emp_code, day.get("employee_name"),
                     day.get("bamboohr_id"), day.get("employee_number"), day.get("department"), e.terminal_alias,
                     e.verify_type, _mapping_label(day), _flags_text(day["flags"])])
    return Sheet("Event Detail", cols, rows)


# --- recorded activity (raw events of every mapping state) --------------------

RECORDED_TITLE = {
    "all": "Recorded Activity — all mapping states",
    "unverified": "Recorded Activity — unmapped / needs review only",
    "conflict": "Recorded Activity — mapping conflicts only",
}
MAPPING_FILTER_LABEL = {
    "all": "All activity", "verified": "Verified", "unverified": "Unmapped / needs review",
    "conflict": "Mapping conflict",
}
STATE_LABEL = {"VERIFIED": "Verified", "UNMAPPED": "Unmapped — needs review", "CONFLICT": "Mapping conflict"}
SEQUENCE_LABEL = {"FIRST": "First recorded fingerprint", "LAST": "Last recorded fingerprint",
                  "INTERMEDIATE": "Intermediate", "SINGLE": "Single Recorded Fingerprint"}


def recorded_event_sheet(events, ident, seqs: dict[str, dict]) -> Sheet:
    """One row per recorded event (oldest first). Unverified events carry only
    the raw ZKBioTime ID — never a name, BHR ID or EMP Number."""
    cols = [Column("Local Date", 12, "date"), Column("Local Time", 11, "time"), Column("ZKBioTime ID", 14),
            Column("Mapping Status", 24), Column("Punch Sequence (whole day)", 22), Column("Team Member Name", 26),
            Column("BHR ID", 12), Column("EMP Number", 14), Column("Department", 20), Column("Terminal", 18),
            Column("Raw State", 10), Column("Verify Type", 11)]
    rows = []
    for e in events:
        r = ident.resolve(e.emp_code, e.site_local_date, e.site_id)
        state = svc.mapping_state(r)
        verified = state == svc.VERIFIED
        seq = seqs.get(e.event_id, {})
        rows.append([e.site_local_date, _time(e.punch_time_local), e.emp_code, STATE_LABEL[state],
                     SEQUENCE_LABEL.get(seq.get("punch_sequence"), ""),
                     r.employee_name if verified else None, r.bamboohr_id if verified else None,
                     r.employee_number if verified else None, r.department if verified else None,
                     e.terminal_alias, e.punch_state, e.verify_type])
    return Sheet("Recorded Events", cols, rows)


def recorded_summary_sheet(counts: dict, start: date, end: date, mapping: str, exported: int) -> Sheet:
    rows: list[list] = [
        ["Date range", f"{start.isoformat()} to {end.isoformat()}"],
        ["Export scope", "Recorded attendance events (raw), not employee-attributed attendance"],
        ["Mapping status filter", MAPPING_FILTER_LABEL[mapping]],
        ["Events in this export", exported],
        ["Recorded events (all mapping states, same filters)", counts["recorded"]],
        ["Verified events", counts["verified"]],
        ["Unmapped events (needs review)", counts["unmapped"]],
        ["Mapping-conflict events (never attributed)", counts["conflict"]],
        ["Note", "Verified + unmapped + conflict = recorded. Each event is classified by the mapping valid on "
                 "its own site-local day. Fingerprints are recorded at an entry-side reader: the first and last "
                 "recorded fingerprint are not a confirmed exit, presence or working hours."],
    ]
    return Sheet("Summary", [Column("Measure", 44), Column("Value", 60, wrap=True)], rows)


# --- Daily Fingerprint Activity Summary (v0.9) ---------------------------------

DAILY_TITLE = "Daily Fingerprint Activity Summary"
EVIDENCE_GROUP = "Recorded evidence"
SCOPE_NOTE = ("Recorded fingerprints from an entry-side reader — not working, paid or on-site hours. The final "
              "fingerprint of a day is not an exit.")
DEFINITIONS = [
    ("Definition: Recorded Span", "Time between the first and last recorded fingerprint of an identity-day. A "
     "measured interval between observations — not a confirmed exit, presence or working hours. Blank for a "
     "Single Recorded Fingerprint (unavailable, never 0)."),
    ("Definition: Single Recorded Fingerprint", "Only one fingerprint was recorded that day: a neutral observation "
     "for optional review, not a violation."),
    ("Definition: Administrative review", REVIEW_NOTE + " An estimated interval is the first recorded fingerprint "
     "to a reviewed declared departure; it is never counted as an event."),
    ("Definition: Identity", "Verified = a team member (all of their ZKBioTime IDs that day). Unmapped and Mapping "
     "conflict rows show the raw ZKBioTime ID only and are never attributed to a person."),
]
DAILY_STATE_LABEL = {"VERIFIED": "Verified", "UNMAPPED": "Unmapped — needs review", "CONFLICT": "Mapping conflict"}


def _span_text(minutes: int | None) -> str:
    return "—, Single Recorded Fingerprint" if minutes is None else f"{minutes // 60}h {minutes % 60:02d}m"


def daily_summary_sheet(rows: list[dict]) -> Sheet:
    ev = EVIDENCE_GROUP
    cols = [Column("Date", 12, "date", group=ev), Column("Identity", 26, group=ev), Column("BHR ID", 12, group=ev),
            Column("EMP Number", 14, group=ev), Column("ZKBioTime ID(s)", 16, group=ev),
            Column("Mapping Status", 22, group=ev), Column("First Recorded Fingerprint", 14, "time", group=ev),
            Column("Last Recorded Fingerprint", 14, "time", group=ev),
            Column("Recorded Span (minutes)", 14, "int", group=ev), Column("Recorded Span", 18, group=ev),
            Column("Punches", 10, "int", group=ev), Column("Single Recorded Fingerprint", 12, group=ev),
            Column("Terminal(s)", 20, wrap=True, group=ev), *REVIEW_COLUMNS]
    out = []
    for r in rows:
        verified = r["mapping_state"] == "VERIFIED"
        out.append([
            date.fromisoformat(r["local_date"]),
            r.get("employee_name") if verified else f"ZKBioTime ID {r['emp_code']}",
            r.get("bamboohr_id"), r.get("employee_number"), ", ".join(r["zk_emp_codes"]),
            DAILY_STATE_LABEL[r["mapping_state"]], _time(r["first_fingerprint_local"]),
            _time(r["last_fingerprint_local"]), r["recorded_span_minutes"], _span_text(r["recorded_span_minutes"]),
            r["punch_count"], "Yes" if r["single"] else "No", ", ".join(r["terminal_names"]),
            *review_cells(r, classification="Single Recorded Fingerprint" if r["single"] else None),
        ])
    return Sheet("Daily Summary", cols, out)


def case_history_sheet(entries: list[tuple[dict, dict]]) -> Sheet:
    """(row, history entry) pairs — the append-only review history."""
    cols = [Column("Date", 12, "date"), Column("Identity", 24), Column("Case ID", 9, "int"), Column("Action", 12),
            Column("From Status", 22), Column("To Status", 22), Column("Version", 9, "int"), Column("By", 20),
            Column("At (UTC)", 18, "datetime"), Column("Note", 48, wrap=True)]
    out = []
    for r, h in entries:
        out.append([date.fromisoformat(r["local_date"]),
                    r.get("employee_name") if r["mapping_state"] == "VERIFIED" else f"ZKBioTime ID {r['emp_code']}",
                    r["review"]["id"], h["action"].title(), STATUS_LABEL.get(h["from_status"] or "", "—"),
                    STATUS_LABEL.get(h["to_status"], h["to_status"]), h["version"], h["actor_name"],
                    datetime.fromisoformat(h["at"]).astimezone(UTC).replace(tzinfo=None), h["note"]])
    return Sheet("Case History", cols, out, empty_message="No review cases in the selection.")


def daily_report_summary(summary: dict, rows: list[dict], start: date, end: date, mapping: str, detail: str,
                         exported_events: int | None) -> Sheet:
    """Source counts and case counts are reported separately — never summed."""
    cases = Counter(r["review"]["status"] for r in rows if r.get("review"))
    stale = sum(1 for r in rows if r.get("review") and r["review"]["stale"])
    lines: list[list] = [
        ["Date range", f"{start.isoformat()} to {end.isoformat()}"],
        ["Report scope", SCOPE_NOTE],
        ["Mapping status filter", MAPPING_FILTER_LABEL.get(mapping, mapping)],
        ["Detail level", {"summary": "Summary", "detailed": "Detailed", "both": "Summary and detail"}[detail]],
        ["— Recorded evidence (source fingerprints) —", ""],
        ["Identity-days in this export", len(rows)],
        ["Recorded fingerprints in this export", sum(r["punch_count"] for r in rows)],
        ["Identity-days, all mapping states (same filters)", summary["identity_days"]],
        ["Recorded fingerprints, all mapping states (same filters)", summary["punches"]],
        ["Verified fingerprints", summary["verified_punches"]],
        ["Unmapped fingerprints (needs review)", summary["unmapped_punches"]],
        ["Mapping-conflict fingerprints (never attributed)", summary["conflict_punches"]],
        ["Single Recorded Fingerprint identity-days", sum(1 for r in rows if r["single"])],
    ]
    if exported_events is not None:
        lines.append(["Fingerprints in Punch Detail", exported_events])
    lines += [
        ["— Administrative review (cases, not fingerprints) —", ""],
        *[[f"Cases: {STATUS_LABEL[s]}", cases.get(s, 0)] for s in ("OPEN", "SUBMITTED", "RESOLVED", "REOPENED")],
        ["Cases needing reassessment", stale],
        ["Identity-days without a case", sum(1 for r in rows if not r.get("review"))],
        ["Note", "Case counts are administrative records and are never added to fingerprint counts. Estimated "
                 "intervals are reviewed declarations, never counted as events, and never replace Recorded Span."],
    ]
    return Sheet("Summary", [Column("Measure", 52), Column("Value", 64, wrap=True)], lines)


def summary_sheet(days: list[dict], start: date, end: date, unmapped: int | None = None) -> Sheet:
    counts = Counter(f for r in days for f in r["flags"])
    flagged = {r["bamboohr_id"] for r in days if r["flags"]}
    rows: list[list] = [
        ["Date range", f"{start.isoformat()} to {end.isoformat()}"],
        ["Team members with activity", len({r["bamboohr_id"] for r in days})],
        ["Team-member days with activity", len(days)],
        ["Attendance events", sum(r["punch_count"] for r in days)],
        ["Team members needing review", len(flagged)],
        ["Single Recorded Fingerprint days", counts.get(ReviewFlag.SINGLE_PUNCH.value, 0)],
    ]
    if unmapped is not None:
        rows.append(["Unmapped punches excluded (see Identity Management)", unmapped])
    rows += [[f"Review flag: {FLAG_LABEL[f]}", counts.get(f, 0)] for f in svc.REVIEW_FLAGS]
    return Sheet("Summary", [Column("Measure", 36), Column("Value", 24)], rows)


# --- metadata ------------------------------------------------------------------


def filter_summary(site_name: str, date_label: str, f: ExportFilters) -> list[tuple[str, str]]:
    labels = {"q": "Team member search", "emp_code": "ZKBioTime ID", "department": "Department",
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

