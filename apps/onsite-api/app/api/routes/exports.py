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
from app.services import attendance_export as ex
from app.services import dashboard_service as svc
from app.services import workforce_directory
from app.services.excel_report import XLSX_MEDIA_TYPE, Column, ReportMeta, Sheet, build_workbook
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
    days = ex.day_rows(db, scope.allowed_site_ids, site, tz, start, end, workforce_directory.load(), f)
    if exceptions_only:
        days = [r for r in days if r["flags"]]
    sheets = [ex.attendance_sheet(days, title="Exception Report" if exceptions_only else "Attendance Report",
                                  with_reasons=exceptions_only)]
    if with_events:
        sheets.append(ex.event_sheet(ex.event_rows(db, scope.allowed_site_ids, site, start, end, days, f.terminal)))
    sheets.append(ex.summary_sheet(days, start, end))
    label = start.isoformat() if start == end else f"{start.isoformat()} to {end.isoformat()}"
    meta = ReportMeta(title=title, generated_by=scope.user.full_name,
                      filters=ex.filter_summary(ex.site_name(db, scope.allowed_site_ids, site), label, f))
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
                    scope: OnsiteScope = Depends(require_onsite_permission(Perm.ATTENDANCE_READ)),
                    db: Session = Depends(get_db)):
    site, tz, today = _site(db, scope, site_id)
    start, end = svc.resolve_range(date_from, date_to, default_days=7, today=today)
    f = ex.ExportFilters(q=q, emp_code=emp_code, department=department, identity_class=identity_class, review=flag,
                         terminal=terminal)
    directory = workforce_directory.load()
    # Exactly the Activity view's selection (all pages), not a re-derivation.
    total, events = svc.select_activity(db, scope.allowed_site_ids, site, start, end, directory, q=q,
                                        department=department, terminal=terminal, identity_class=identity_class,
                                        flag=flag, tz=tz, emp_code=emp_code, offset=0,
                                        limit=ex.MAX_EXPORT_EVENTS + 1)
    if total > ex.MAX_EXPORT_EVENTS:
        raise ex.too_large(total, ex.MAX_EXPORT_EVENTS)
    pairs = {(e.site_local_date.isoformat(), e.emp_code) for e in events}
    # Day rows for exactly those employee-days (identity/flags are per day already).
    days = [r for r in ex.day_rows(db, scope.allowed_site_ids, site, tz, start, end, directory,
                                   ex.ExportFilters(q=q, emp_code=emp_code, department=department))
            if (r["local_date"], r["emp_code"]) in pairs]
    sheets = [ex.attendance_sheet(days), ex.event_sheet(ex.pair_events(events, {(r["local_date"], r["emp_code"]): r
                                                                                for r in days})),
              ex.summary_sheet(days, start, end)]
    label = start.isoformat() if start == end else f"{start.isoformat()} to {end.isoformat()}"
    meta = ReportMeta(title="Attendance Activity Report", generated_by=scope.user.full_name,
                      filters=ex.filter_summary(ex.site_name(db, scope.allowed_site_ids, site), label, f))
    return _xlsx(build_workbook(meta, sheets), ex.filename("Attendance", start, end, department, emp_code))


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
    rows = [[r["emp_code"], r.get("employee_name"), r.get("department"), r.get("employment_status"),
             ex.IDENTITY_LABEL.get(r.get("identity_class") or "", "Directory unavailable"),
             r["activity_days"], r["events"], r["review_flags"],
             ex._local(r["last_activity_local"]).replace(tzinfo=None) if r["last_activity_local"] else None]
            for r in data["items"]]
    cols = [Column("Employee Number", 16), Column("Employee Name", 26), Column("Department", 20),
            Column("Employment Status", 14), Column("Identity Classification", 24), Column("Activity Days", 12, "int"),
            Column("Attendance Events", 12, "int"), Column("Review Flags", 12, "int"),
            Column("Last Activity (site local)", 18, "datetime")]
    summary = Sheet("Summary", [Column("Measure", 36), Column("Value", 24)], [
        ["Date range", f"{start.isoformat()} to {end.isoformat()}"],
        ["Employees listed", len(rows)],
        ["Employees with activity", sum(1 for r in data["items"] if r["events"])],
        ["Attendance events", sum(r["events"] for r in data["items"])],
        ["Employees with review flags", sum(1 for r in data["items"] if r["review_flags"])],
    ])
    f = ex.ExportFilters(q=q, emp_code=emp_code, department=department, identity_class=identity_class,
                         employment_status=employment_status)
    filters = ex.filter_summary(ex.site_name(db, scope.allowed_site_ids, site),
                                f"{start.isoformat()} to {end.isoformat()}", f)
    filters.append(("Activity", {"with_activity": "Activity recorded", "no_activity": "No activity recorded"}
                    .get(activity or "", "Everyone")))
    meta = ReportMeta(title="Employee Activity Report", generated_by=scope.user.full_name, filters=filters)
    return _xlsx(build_workbook(meta, [Sheet("Employees", cols, rows), summary]),
                 ex.filename("Employees", start, end, department, emp_code))


@router.get("/dashboard/overview/export")
def export_overview(site_id: str | None = None, date_: date | None = Query(None, alias="date"),
                    scope: OnsiteScope = Depends(require_onsite_permission(Perm.DASHBOARD_READ)),
                    db: Session = Depends(get_db)):
    site, tz, today = _site(db, scope, site_id)
    day = date_ or today
    allowed = scope.allowed_site_ids
    ov = svc.overview(db, allowed, site, tz, day, workforce_directory.load())
    k = ov["kpis"]
    summary = Sheet("Summary", [Column("Measure", 36), Column("Value", 24)], [
        ["Date", day.isoformat()],
        ["Employees with activity", k["employees_with_activity"]],
        ["Attendance events", k["total_events"]],
        ["Employees needing review", k["employees_needing_review"]],
        ["Single-activity employees", k["single_punch_employees"]],
        ["Unmatched codes", k["unmatched_codes"]],
        ["Feed state", (k["feed_state"] or "Unknown").replace("_", " ").title()],
        *[[f"Review flag: {ex.FLAG_LABEL[f]}", n] for f, n in ov["review_breakdown"].items()],
    ])
    hours = svc.hourly(db, allowed, site, day)["hours"]
    hourly = Sheet("Hourly Activity", [Column("Hour", 10), Column("Attendance Events", 14, "int"),
                                       Column("Employees", 12, "int")],
                   [[f"{h['hour']:02d}:00", h["events"], h["employees"]] for h in hours])
    start, end = svc.resolve_range(None, day, default_days=30, today=day)
    trend = Sheet("30-Day Trend", [Column("Date", 12, "date"), Column("Attendance Events", 14, "int"),
                                    Column("Employees", 12, "int")],
                  [[date.fromisoformat(d["date"]), d["events"], d["employees"]]
                   for d in svc.trend(db, allowed, site, start, end)["days"]])
    meta = ReportMeta(title="Attendance Overview Report", generated_by=scope.user.full_name,
                      filters=[("Site", ex.site_name(db, allowed, site)), ("Date", day.isoformat())])
    return _xlsx(build_workbook(meta, [summary, hourly, trend]), ex.filename("Overview", day, day))

