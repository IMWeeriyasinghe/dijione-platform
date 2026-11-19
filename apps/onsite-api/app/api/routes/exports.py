"""Diji On-site Excel exports (.xlsx). Each export takes the same filters as
its dashboard view and is gated by the same permission; site scope and every
filter are re-applied server-side — nothing is trusted from the browser."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import OnsiteScope, require_onsite_permission
from app.core.constants import Perm
from app.db.session import get_db
from app.repositories.attendance_repository import AttendanceRepository
from app.services import attendance_export as ex
from app.services import attendance_review_service as reviews
from app.services import dashboard_service as svc
from app.services import workforce_directory
from app.services.excel_report import XLSX_MEDIA_TYPE, Column, ReportMeta, Sheet, build_workbook
from app.services.identity_resolution import MappingIndex
from app.services.time_derivation import site_today

router = APIRouter(prefix="/api/onsite", tags=["onsite-exports"])

_FLAG = "^(" + "|".join(svc.REVIEW_FLAGS) + ")$"
_IDENTITY = "^(" + "|".join(svc.IDENTITY_CLASSES) + ")$"
_REVIEW = "^(needs_review|no_flags|" + "|".join(svc.REVIEW_FLAGS) + ")$"


def _xlsx(content: bytes, name: str) -> Response:
    return Response(content, media_type=XLSX_MEDIA_TYPE,
                    headers={"Content-Disposition": f'attachment; filename="{name}"',
                             "Cache-Control": "no-store"})


def _site(db, scope: OnsiteScope, site_id: str | None):
    site, tz = svc.resolve_site(db, scope.allowed_site_ids, site_id)
    return site, tz, site_today(tz)


def _attendance_workbook(db, scope: OnsiteScope, *, report: str, title: str, site: str, tz, start: date, end: date,
                         f: ex.ExportFilters, with_events: bool = True, exceptions_only: bool = False) -> Response:
    directory = workforce_directory.load()
    days = ex.day_rows(db, scope.allowed_site_ids, site, tz, start, end, directory, f)
    if exceptions_only:
        days = [r for r in days if r["flags"]]
        index = MappingIndex.load(db, allowed_site_ids=scope.allowed_site_ids, directory=directory)
        reviews.attach(db, scope.allowed_site_ids, site, tz, index, days, start, end)
    sheets = [ex.attendance_sheet(days, title="Exception Report" if exceptions_only else "Attendance Report",
                                  with_reasons=exceptions_only, with_review=exceptions_only)]
    if with_events:
        sheets.append(ex.event_sheet(ex.event_rows(db, scope.allowed_site_ids, site, start, end, days, f.terminal)))
    sheets.append(ex.summary_sheet(days, start, end,
                                   ex.unmapped_punches(db, scope.allowed_site_ids, site, start, end,
                                                       workforce_directory.load())))
    label = start.isoformat() if start == end else f"{start.isoformat()} to {end.isoformat()}"
    meta = ReportMeta(title=title, generated_by=scope.user.full_name, report_type=title, time_zone=tz,
                      filters=ex.filter_summary(ex.site_name(db, scope.allowed_site_ids, site), label, f),
                      definitions=ex.DEFINITIONS[:2] + ([ex.DEFINITIONS[2]] if exceptions_only else []))
    return _xlsx(build_workbook(meta, sheets), ex.filename(report, start, end, f.department, f.emp_code))


@router.get("/today/export")
def export_today(site_id: str | None = None, date_: date | None = Query(None, alias="date"), q: str | None = None,
                 emp_code: str | None = None, department: str | None = None,
                 identity_class: str | None = Query(None, pattern=_IDENTITY),
                 review: str | None = Query(None, pattern=_REVIEW),
                 scope: OnsiteScope = Depends(require_onsite_permission(Perm.ATTENDANCE_READ)),
                 db: Session = Depends(get_db)):
    site, tz, today = _site(db, scope, site_id)
    day = date_ or today
    f = ex.ExportFilters(q=q, emp_code=emp_code, department=department, identity_class=identity_class, review=review)
    return _attendance_workbook(db, scope, report="Attendance", title="Attendance Activity Report", site=site, tz=tz,
                                start=day, end=day, f=f)


@router.get("/activity/export")
def export_activity(site_id: str | None = None, date_from: date | None = None, date_to: date | None = None,
                    q: str | None = None, emp_code: str | None = None, department: str | None = None,
                    terminal: str | None = None, identity_class: str | None = Query(None, pattern=_IDENTITY),
                    flag: str | None = Query(None, pattern=_FLAG),
                    hour: int | None = Query(None, ge=0, le=23),
                    mapping: str | None = Query(None, pattern="^(" + "|".join(svc.MAPPING_FILTERS) + ")$"),
                    scope: OnsiteScope = Depends(require_onsite_permission(Perm.ATTENDANCE_READ)),
                    db: Session = Depends(get_db)):
    site, tz, today = _site(db, scope, site_id)
    start, end = svc.resolve_range(date_from, date_to, default_days=7, today=today)
    f = ex.ExportFilters(q=q, emp_code=emp_code, department=department, identity_class=identity_class, review=flag,
                         terminal=terminal)
    directory = workforce_directory.load()
    index = MappingIndex.load(db, allowed_site_ids=scope.allowed_site_ids, directory=directory)
    # Exactly the Activity view's selection (all pages), not a re-derivation.
    total, events = svc.select_activity(db, scope.allowed_site_ids, site, start, end, directory, q=q,
                                        department=department, terminal=terminal, identity_class=identity_class,
                                        flag=flag, tz=tz, emp_code=emp_code, offset=0,
                                        limit=ex.MAX_EXPORT_EVENTS + 1, hour=hour, mapping=mapping, index=index)
    if total > ex.MAX_EXPORT_EVENTS:
        raise ex.too_large(total, ex.MAX_EXPORT_EVENTS)
    label = start.isoformat() if start == end else f"{start.isoformat()} to {end.isoformat()}"
    if mapping not in (None, "verified"):
        # Recorded events of every requested mapping state — explicitly a raw-event export, not attendance.
        title = ex.RECORDED_TITLE[mapping]
        plan = svc._mapping_plan(db, scope.allowed_site_ids, site, start, end, directory, index, mapping="all", q=q,
                                 department=department, terminal=terminal, identity_class=identity_class, flag=flag,
                                 tz=tz, emp_code=emp_code, hour=hour, bamboohr_id=None)
        counts = svc.activity_counts(db, scope.allowed_site_ids, site, plan)
        ident = svc.Identity(db, scope.allowed_site_ids, directory, site, index=index)
        seqs = svc.punch_sequences(db, scope.allowed_site_ids, site, index, events)
        sheets = [ex.recorded_event_sheet(list(reversed(events)), ident, seqs),
                  ex.recorded_summary_sheet(counts, start, end, mapping, total)]
        meta = ReportMeta(title=title, generated_by=scope.user.full_name, report_type="Recorded Activity (raw events)",
                          time_zone=tz, filters=[*ex.filter_summary(ex.site_name(db, scope.allowed_site_ids, site), label, f),
                                   ("Mapping status", ex.MAPPING_FILTER_LABEL[mapping])])
        return _xlsx(build_workbook(meta, sheets), ex.filename("Recorded-Activity", start, end, mapping, emp_code))
    pairs = {(e.site_local_date.isoformat(), e.emp_code) for e in events}
    # Verified employee-day rows for exactly those (date, ZKBioTime ID) pairs.
    days = [r for r in ex.day_rows(db, scope.allowed_site_ids, site, tz, start, end, directory, ex.ExportFilters())
            if any((r["local_date"], c) in pairs for c in r["zk_emp_codes"])]
    sheets = [ex.attendance_sheet(days), ex.event_sheet(ex.pair_events(events, ex._by_code_day(days))),
              ex.summary_sheet(days, start, end,
                               ex.unmapped_punches(db, scope.allowed_site_ids, site, start, end, directory))]
    meta = ReportMeta(title="Attendance Activity Report", generated_by=scope.user.full_name,
                      report_type="Verified Attendance", time_zone=tz, definitions=ex.DEFINITIONS[:2],
                      filters=ex.filter_summary(ex.site_name(db, scope.allowed_site_ids, site), label, f))
    return _xlsx(build_workbook(meta, sheets), ex.filename("Attendance", start, end, department, emp_code))


@router.get("/activity/daily/export")
def export_activity_daily(site_id: str | None = None, date_from: date | None = None, date_to: date | None = None,
                          mapping: str = Query("all", pattern="^(" + "|".join(svc.MAPPING_FILTERS) + ")$"),
                          q: str | None = None, emp_code: str | None = None, bamboohr_id: str | None = None,
                          terminal: str | None = None,
                          review_status: str | None = Query(None, pattern="^(" + "|".join(svc.REVIEW_STATUS_FILTERS)
                                                            + ")$"),
                          detail: str = Query("summary", pattern="^(summary|detailed|both)$"),
                          scope: OnsiteScope = Depends(require_onsite_permission(Perm.ATTENDANCE_READ)),
                          db: Session = Depends(get_db)):
    """Daily Fingerprint Activity Summary: exactly the Daily view's selection
    (all pages), with Recorded evidence and Administrative review kept in
    separate column groups, an optional Punch Detail and Case History, and a
    Summary that reports fingerprint counts and case counts separately."""
    site, tz, today = _site(db, scope, site_id)
    start, end = svc.resolve_range(date_from, date_to, default_days=7, today=today)
    directory = workforce_directory.load()
    index = MappingIndex.load(db, allowed_site_ids=scope.allowed_site_ids, directory=directory)
    rows, summary = svc.daily_rows(db, scope.allowed_site_ids, site, tz, start, end, directory, mapping=mapping, q=q,
                                   emp_code=emp_code, bamboohr_id=bamboohr_id, terminal=terminal,
                                   review_status=review_status, index=index)
    if len(rows) > ex.MAX_EXPORT_DAY_ROWS:
        raise ex.too_large(len(rows), ex.MAX_EXPORT_DAY_ROWS)
    rows.sort(key=lambda r: (r["local_date"], (r.get("employee_name") or "~").lower(), r["emp_code"]))
    sheets = []
    if detail in ("summary", "both"):
        sheets.append(ex.daily_summary_sheet(rows))
    exported_events = None
    if detail in ("detailed", "both"):
        windows = [(c, date.fromisoformat(r["local_date"]), date.fromisoformat(r["local_date"]))
                   for r in rows for c in r["zk_emp_codes"]]
        total, events = (0, []) if not windows else AttendanceRepository(db).events_page(
            allowed_site_ids=scope.allowed_site_ids, site_id=site, date_from=start, date_to=end,
            code_windows=windows, offset=0, limit=ex.MAX_EXPORT_EVENTS + 1, oldest_first=True)
        if total > ex.MAX_EXPORT_EVENTS:
            raise ex.too_large(total, ex.MAX_EXPORT_EVENTS)
        exported_events = total
        ident = svc.Identity(db, scope.allowed_site_ids, directory, site, index=index)
        seqs = svc.punch_sequences(db, scope.allowed_site_ids, site, index, events)
        punch = ex.recorded_event_sheet(events, ident, seqs)
        punch.title = "Punch Detail"
        sheets.append(punch)
        sheets.append(ex.case_history_sheet([(r, h) for r in rows if r.get("review")
                                             for h in reviews.history(db, r["review"]["id"])]))
    sheets.append(ex.daily_report_summary(summary, rows, start, end, mapping, detail, exported_events))
    label = start.isoformat() if start == end else f"{start.isoformat()} to {end.isoformat()}"
    f = ex.ExportFilters(q=q, emp_code=emp_code, terminal=terminal)
    filters = [*ex.filter_summary(ex.site_name(db, scope.allowed_site_ids, site), label, f),
               ("Mapping status", ex.MAPPING_FILTER_LABEL[mapping]),
               ("Review status", review_status or "All")]
    if bamboohr_id:
        filters.append(("BHR ID", bamboohr_id))
    meta = ReportMeta(title=ex.DAILY_TITLE, generated_by=scope.user.full_name, report_type=ex.DAILY_TITLE,
                      time_zone=tz, filters=filters, definitions=ex.DEFINITIONS)
    return _xlsx(build_workbook(meta, sheets), ex.filename("Daily-Fingerprint-Activity", start, end, mapping,
                                                           emp_code or bamboohr_id))


@router.get("/exceptions/export")
def export_exceptions(site_id: str | None = None, date_from: date | None = None, date_to: date | None = None,
                      flag: str | None = Query(None, pattern=_FLAG), q: str | None = None,
                      emp_code: str | None = None, department: str | None = None,
                      identity_class: str | None = Query(None, pattern=_IDENTITY),
                      scope: OnsiteScope = Depends(require_onsite_permission(Perm.EXCEPTIONS_READ)),
                      db: Session = Depends(get_db)):
    site, tz, today = _site(db, scope, site_id)
    start, end = svc.resolve_range(date_from, date_to, default_days=7, today=today)
    f = ex.ExportFilters(q=q, emp_code=emp_code, department=department, identity_class=identity_class,
                         review=flag or "needs_review")
    return _attendance_workbook(db, scope, report="Exceptions", title="Attendance Exceptions Report", site=site, tz=tz,
                                start=start, end=end, f=f, exceptions_only=True)


@router.get("/employees/export")
def export_employees(site_id: str | None = None, date_from: date | None = None, date_to: date | None = None,
                     q: str | None = None, emp_code: str | None = None, department: str | None = None,
                     employment_status: str | None = None, identity_class: str | None = Query(None, pattern=_IDENTITY),
                     activity: str | None = Query(None, pattern="^(with_activity|no_activity)$"),
                     scope: OnsiteScope = Depends(require_onsite_permission(Perm.ATTENDANCE_READ)),
                     db: Session = Depends(get_db)):
    site, tz, today = _site(db, scope, site_id)
    start, end = svc.resolve_range(date_from, date_to, default_days=30, today=today)
    data = svc.employees(db, scope.allowed_site_ids, site, tz, start, end, workforce_directory.load(), q=q,
                         department=department, status_filter=employment_status, activity_filter=activity,
                         page=1, page_size=ex.MAX_EXPORT_DAY_ROWS + 1, emp_code=emp_code, identity_class=identity_class)
    if data["total"] > ex.MAX_EXPORT_DAY_ROWS:
        raise ex.too_large(data["total"], ex.MAX_EXPORT_DAY_ROWS)
    rows = [[r.get("employee_name"), r.get("bamboohr_id"), r.get("employee_number"),
             ", ".join(r.get("zk_emp_codes") or []), r.get("department"), r.get("employment_status"),
             ex.MAPPING_LABEL.get(r.get("mapping_status") or "", ""),
             r["activity_days"], r["events"], r["review_flags"],
             ex._local(r["last_activity_local"]).replace(tzinfo=None) if r["last_activity_local"] else None]
            for r in data["items"]]
    cols = [Column("Team Member Name", 26), Column("BHR ID", 14), Column("EMP Number", 16),
            Column("ZKBioTime ID(s)", 16), Column("Department", 20), Column("Employment Status", 14),
            Column("Mapping Status", 22), Column("Activity Days", 12, "int"),
            Column("Attendance Events", 12, "int"), Column("Review Flags", 12, "int"),
            Column("Last Activity (site local)", 18, "datetime")]
    summary = Sheet("Summary", [Column("Measure", 36), Column("Value", 24)], [
        ["Date range", f"{start.isoformat()} to {end.isoformat()}"],
        ["Team members listed", len(rows)],
        ["Team members with activity", sum(1 for r in data["items"] if r["events"])],
        ["Attendance events", sum(r["events"] for r in data["items"])],
        ["Team members with review flags", sum(1 for r in data["items"] if r["review_flags"])],
        ["Unmapped punches excluded (see Identity Management)",
         ex.unmapped_punches(db, scope.allowed_site_ids, site, start, end, workforce_directory.load())],
    ])
    f = ex.ExportFilters(q=q, emp_code=emp_code, department=department, identity_class=identity_class,
                         employment_status=employment_status)
    filters = ex.filter_summary(ex.site_name(db, scope.allowed_site_ids, site),
                                f"{start.isoformat()} to {end.isoformat()}", f)
    filters.append(("Activity", {"with_activity": "Activity recorded", "no_activity": "No activity recorded"}
                    .get(activity or "", "Everyone")))
    meta = ReportMeta(title="Team Member Activity Report", generated_by=scope.user.full_name, filters=filters,
                      report_type="Team Member Attendance", time_zone=tz)
    return _xlsx(build_workbook(meta, [Sheet("Team Members", cols, rows), summary]),
                 ex.filename("Team-Members", start, end, department, emp_code))


@router.get("/dashboard/overview/export")
def export_overview(site_id: str | None = None, date_: date | None = Query(None, alias="date"),
                    scope: OnsiteScope = Depends(require_onsite_permission(Perm.DASHBOARD_READ)),
                    db: Session = Depends(get_db)):
    site, tz, today = _site(db, scope, site_id)
    day = date_ or today
    allowed = scope.allowed_site_ids
    ov = svc.overview(db, allowed, site, tz, day, workforce_directory.load())
    k = ov["kpis"]

    def extreme(block) -> str:
        if not block:
            return "None recorded"
        e = block["entries"][0]
        who = e["employee_name"] if e["mapping_state"] == "VERIFIED" else f"ZKBioTime ID {e['zk_emp_code']}"
        tied = f" (+{block['tied'] - 1} tied)" if block["tied"] > 1 else ""
        return f"{block['local_time'][11:19]}, {who}{tied}"

    summary = Sheet("Summary", [Column("Measure", 44), Column("Value", 40)], [
        ["Date", day.isoformat()],
        ["Team members with activity", k["employees_with_activity"]],
        ["Attendance events", k["total_events"]],
        ["Team members needing review", k["employees_needing_review"]],
        ["Single Recorded Fingerprint team members", k["single_punch_employees"]],
        ["Feed state", (k["feed_state"] or "Unknown").replace("_", " ").title()],
        ["Recorded events (all mapping states)", k["recorded_events"]],
        ["Verified events", k["verified_events"]],
        ["Unmapped events (needs review)", k["unmapped_events"]],
        ["Mapping-conflict events", k["conflict_events"]],
        ["Earliest Recorded Fingerprint", extreme((ov.get("extremes") or {}).get("earliest"))],
        ["Latest Recorded Fingerprint", extreme((ov.get("extremes") or {}).get("latest"))],
        *[[f"Review flag: {ex.FLAG_LABEL[f]}", n] for f, n in ov["review_breakdown"].items()],
    ])
    hours = svc.hourly(db, allowed, site, day, directory=workforce_directory.load())["hours"]
    hourly = Sheet("Hourly Activity", [Column("Hour", 10), Column("Recorded events", 14, "int"),
                                       Column("Verified events", 12, "int"), Column("Unmapped events", 12, "int"),
                                       Column("Conflict events", 12, "int"), Column("Team Members", 12, "int")],
                   [[f"{h['hour']:02d}:00", h["events"], h["verified_events"], h["unmapped_events"],
                     h["conflict_events"], h["employees"]] for h in hours])
    start, end = svc.resolve_range(None, day, default_days=30, today=day)
    trend = Sheet("30-Day Trend", [Column("Date", 12, "date"), Column("Recorded events", 14, "int"),
                                    Column("Verified events", 12, "int"), Column("Unmapped events", 12, "int"),
                                    Column("Conflict events", 12, "int"), Column("Team Members", 12, "int")],
                  [[date.fromisoformat(d["date"]), d["events"], d["verified_events"], d["unmapped_events"],
                    d["conflict_events"], d["employees"]]
                   for d in svc.trend(db, allowed, site, start, end, workforce_directory.load())["days"]])
    meta = ReportMeta(title="Attendance Overview Report", generated_by=scope.user.full_name,
                      report_type="Overview summary (single day)", time_zone=tz, definitions=ex.DEFINITIONS[:1],
                      filters=[("Site", ex.site_name(db, allowed, site)), ("Date", day.isoformat())])
    return _xlsx(build_workbook(meta, [summary, hourly, trend]), ex.filename("Overview", day, day))

