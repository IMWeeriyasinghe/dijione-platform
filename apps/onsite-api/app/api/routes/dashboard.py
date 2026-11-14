"""Diji On-site Dashboard V1 API — aggregates computed server-side from the
On-site mirror. Every read is scoped to the caller's enabled-site allow-list
(unknown/disabled site -> 404) and gated by an On-site permission."""

from __future__ import annotations

import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import OnsiteScope, require_onsite_permission
from app.core.constants import Perm
from app.db.session import get_db
from app.services import dashboard_service as svc
from app.services import employee_photos, legacy_contract, workforce_directory
from app.services.identity_resolution import MappingIndex
from app.services.time_derivation import site_today

router = APIRouter(prefix="/api/onsite", tags=["onsite-dashboard"])

_FLAG_PATTERN = "^(" + "|".join(svc.REVIEW_FLAGS) + ")$"
_IDENTITY_PATTERN = "^(" + "|".join(svc.IDENTITY_CLASSES) + ")$"


def _site_and_day(db, scope: OnsiteScope, site_id: str | None, day: date | None) -> tuple[str, str | None, date]:
    site, tz = svc.resolve_site(db, scope.allowed_site_ids, site_id)
    return site, tz, day or site_today(tz)


def _optional_range(date_from: date | None, date_to: date | None, day: date) -> tuple[date, date]:
    """A period (``date_from``..``date_to``, capped at MAX_RANGE_DAYS) when
    given, otherwise the single day ``day``."""
    if date_from is None and date_to is None:
        return day, day
    return svc.resolve_range(date_from, date_to, default_days=1, today=day)


@router.get("/sites")
def sites(scope: OnsiteScope = Depends(require_onsite_permission(Perm.DASHBOARD_READ)), db: Session = Depends(get_db)):
    directory = workforce_directory.load()
    departments = sorted({e["department"] for e in directory.entries if e.get("department")}) if directory.available else []
    return [{**s, "departments": departments} for s in svc.list_sites(db, scope.allowed_site_ids)]


@router.get("/dashboard/overview")
def overview(site_id: str | None = None, date_: date | None = Query(None, alias="date"),
             date_from: date | None = None, date_to: date | None = None,
             scope: OnsiteScope = Depends(require_onsite_permission(Perm.DASHBOARD_READ)), db: Session = Depends(get_db)):
    site, tz, day = _site_and_day(db, scope, site_id, date_)
    start, end = _optional_range(date_from, date_to, day)
    return svc.overview(db, scope.allowed_site_ids, site, tz, start, workforce_directory.load(), date_to=end,
                        include_operational=scope.has(Perm.HEALTH_READ) or scope.has(Perm.IDENTITY_READ))


@router.get("/dashboard/hourly-activity")
def hourly_activity(site_id: str | None = None, date_: date | None = Query(None, alias="date"),
                    date_from: date | None = None, date_to: date | None = None,
                    scope: OnsiteScope = Depends(require_onsite_permission(Perm.DASHBOARD_READ)),
                    db: Session = Depends(get_db)):
    site, _tz, day = _site_and_day(db, scope, site_id, date_)
    start, end = _optional_range(date_from, date_to, day)
    return svc.hourly(db, scope.allowed_site_ids, site, start, end, workforce_directory.load())


@router.get("/dashboard/activity-trend")
def activity_trend(site_id: str | None = None, days: int = Query(30, ge=1, le=svc.MAX_RANGE_DAYS),
                   date_to: date | None = None,
                   scope: OnsiteScope = Depends(require_onsite_permission(Perm.DASHBOARD_READ)),
                   db: Session = Depends(get_db)):
    site, tz, today = _site_and_day(db, scope, site_id, None)
    start, end = svc.resolve_range(None, date_to, default_days=days, today=today)
    return svc.trend(db, scope.allowed_site_ids, site, start, end, workforce_directory.load())


@router.get("/dashboard/recent-activity")
def recent_activity(site_id: str | None = None, limit: int = Query(15, ge=1, le=50),
                    scope: OnsiteScope = Depends(require_onsite_permission(Perm.DASHBOARD_READ)),
                    db: Session = Depends(get_db)):
    site, tz, today = _site_and_day(db, scope, site_id, None)
    start, end = svc.resolve_range(None, today, default_days=svc.MAX_RANGE_DAYS, today=today)
    return svc.activity(db, scope.allowed_site_ids, site, start, end, workforce_directory.load(), q=None,
                        department=None, terminal=None, identity_class=None, flag=None, page=1, page_size=limit,
                        technical=False, tz=tz)


@router.get("/today")
def today(site_id: str | None = None, date_: date | None = Query(None, alias="date"), q: str | None = None,
          department: str | None = None, review: str | None = None, emp_code: str | None = None,
          bamboohr_id: str | None = None, identity_class: str | None = Query(None, pattern=_IDENTITY_PATTERN),
          sort: str = Query("first_activity", pattern="^-?(first_activity|latest_activity|punch_count|span|employee|flags)$"),
          page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=200),
          scope: OnsiteScope = Depends(require_onsite_permission(Perm.ATTENDANCE_READ)), db: Session = Depends(get_db)):
    if review and review not in ("needs_review", "no_flags", *svc.REVIEW_FLAGS):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown review filter")
    site, tz, day = _site_and_day(db, scope, site_id, date_)
    return svc.today_view(db, scope.allowed_site_ids, site, tz, day, workforce_directory.load(), q=q,
                          department=department, review=review, sort=sort, page=page, page_size=page_size,
                          emp_code=emp_code, identity_class=identity_class, bamboohr_id=bamboohr_id)


@router.get("/activity")
def activity(site_id: str | None = None, date_from: date | None = None, date_to: date | None = None,
             q: str | None = None, department: str | None = None, terminal: str | None = None,
             emp_code: str | None = None, bamboohr_id: str | None = None,
             identity_class: str | None = Query(None, pattern=_IDENTITY_PATTERN),
             flag: str | None = Query(None, pattern=_FLAG_PATTERN),
             hour: int | None = Query(None, ge=0, le=23, description="Site-local clock hour on every date in the range"),
             sort: str = Query("-time", pattern="^-?time$"),
             page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=200),
             fmt: str = Query("json", alias="format", pattern="^(json|csv)$"),
             scope: OnsiteScope = Depends(require_onsite_permission(Perm.ATTENDANCE_READ)), db: Session = Depends(get_db)):
    site, tz, today_ = _site_and_day(db, scope, site_id, None)
    start, end = svc.resolve_range(date_from, date_to, default_days=7, today=today_)
    technical = scope.has(Perm.HEALTH_READ)
    if fmt == "csv":
        page, page_size = 1, 50_000  # bounded by the 92-day range cap
    data = svc.activity(db, scope.allowed_site_ids, site, start, end, workforce_directory.load(), q=q,
                        department=department, terminal=terminal, identity_class=identity_class, flag=flag,
                        page=page, page_size=page_size, technical=technical, tz=tz, emp_code=emp_code,
                        hour=hour, oldest_first=sort == "time", bamboohr_id=bamboohr_id)
    if fmt == "json":
        return data
    if data["total"] > page_size:  # never silently truncate the CSV
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            "Too many rows for CSV — narrow the date range or add filters.")
    cols = ["local_time", "emp_code", "employee_name", "department", "terminal", "area", "identity_class",
            "punch_state_raw", "tz_consistent"]
    if technical:
        cols += ["event_id", "source_epoch", "source_transaction_id", "verify_type"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for row in data["items"]:
        w.writerow([row.get(c, "") if row.get(c) is not None else "" for c in cols])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="onsite-activity-{start}-{end}.csv"'})


@router.get("/employees")
def employees(site_id: str | None = None, date_from: date | None = None, date_to: date | None = None,
              q: str | None = None, department: str | None = None, employment_status: str | None = None,
              emp_code: str | None = None, bamboohr_id: str | None = None,
              identity_class: str | None = Query(None, pattern=_IDENTITY_PATTERN),
              activity: str | None = Query(None, pattern="^(with_activity|no_activity)$"),
              sort: str = Query("-events", pattern="^-?(events|activity_days|review_flags|employee|last_activity)$"),
              page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=200),
              scope: OnsiteScope = Depends(require_onsite_permission(Perm.ATTENDANCE_READ)), db: Session = Depends(get_db)):
    site, tz, today_ = _site_and_day(db, scope, site_id, None)
    start, end = svc.resolve_range(date_from, date_to, default_days=30, today=today_)
    return svc.employees(db, scope.allowed_site_ids, site, tz, start, end, workforce_directory.load(), q=q,
                         department=department, status_filter=employment_status, activity_filter=activity,
                         page=page, page_size=page_size, emp_code=emp_code, identity_class=identity_class,
                         sort=sort, bamboohr_id=bamboohr_id)


def _photo_response(photo) -> Response:
    if photo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No photo available")
    return Response(photo.content, media_type=photo.content_type,
                    headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})


def _verified_at_allowed_site(db, scope: OnsiteScope, bamboohr_id: str) -> bool:
    index = MappingIndex.load(db, allowed_site_ids=scope.allowed_site_ids, directory=workforce_directory.load())
    return bool(index.periods_for_employee(bamboohr_id))


@router.get("/employees/by-id/{bamboohr_id}/photo")
def employee_photo_by_id(bamboohr_id: str,
                         scope: OnsiteScope = Depends(require_onsite_permission(Perm.ATTENDANCE_READ)),
                         db: Session = Depends(get_db)) -> Response:
    """Photo of a verified employee (a verified mapping at a site in scope is
    required — the directory is never browsable through this route). 404
    renders as initials."""
    if not _verified_at_allowed_site(db, scope, bamboohr_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No photo available")
    return _photo_response(employee_photos.photo_for_employee(bamboohr_id))


@router.get("/employees/by-id/{bamboohr_id}")
def employee_detail_by_id(bamboohr_id: str, site_id: str | None = None, date_from: date | None = None,
                          date_to: date | None = None, include_events: bool = True,
                          scope: OnsiteScope = Depends(require_onsite_permission(Perm.ATTENDANCE_READ)),
                          db: Session = Depends(get_db)):
    site, tz, today_ = _site_and_day(db, scope, site_id, None)
    start, end = svc.resolve_range(date_from, date_to, default_days=30, today=today_)
    return svc.employee_detail(db, scope.allowed_site_ids, site, tz, bamboohr_id, start, end,
                               workforce_directory.load(), technical=scope.has(Perm.HEALTH_READ),
                               include_events=include_events)


# --- LEGACY code-addressed routes (ONSITE_LEGACY_CONTRACT; removed in API N+2) ---------------


@router.get("/employees/{emp_code}/photo", dependencies=[Depends(legacy_contract.require_legacy_contract)])
def employee_photo(emp_code: str, scope: OnsiteScope = Depends(require_onsite_permission(Perm.ATTENDANCE_READ)),
                   db: Session = Depends(get_db)) -> Response:
    """LEGACY: photo of the employee who VERIFIABLY owns this ZKBioTime ID today
    at a site in scope. Never resolved through Employee Number equality."""
    bid = legacy_contract.employee_owning_code_today(db, scope.allowed_site_ids, emp_code)
    return _photo_response(employee_photos.photo_for_employee(bid) if bid else None)


@router.get("/employees/{emp_code}", dependencies=[Depends(legacy_contract.require_legacy_contract)])
def employee_detail(emp_code: str, site_id: str | None = None, date_from: date | None = None,
                    date_to: date | None = None, include_events: bool = True,
                    scope: OnsiteScope = Depends(require_onsite_permission(Perm.ATTENDANCE_READ)),
                    db: Session = Depends(get_db)):
    """LEGACY: the verified employee who owned this ZKBioTime ID in the period
    (404 when unverified); the profile covers all of that employee's IDs."""
    site, tz, today_ = _site_and_day(db, scope, site_id, None)
    start, end = svc.resolve_range(date_from, date_to, default_days=30, today=today_)
    directory = workforce_directory.load()
    bid = svc.employee_for_code(db, scope.allowed_site_ids, site, emp_code, start, end, directory)
    if bid is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team member not found")
    return svc.employee_detail(db, scope.allowed_site_ids, site, tz, bid, start, end, directory,
                               technical=scope.has(Perm.HEALTH_READ), include_events=include_events)


@router.get("/exceptions")
def exceptions(site_id: str | None = None, date_from: date | None = None, date_to: date | None = None,
               flag: str | None = Query(None, pattern=_FLAG_PATTERN), q: str | None = None,
               emp_code: str | None = None, department: str | None = None, bamboohr_id: str | None = None,
               identity_class: str | None = Query(None, pattern=_IDENTITY_PATTERN),
               sort: str = Query("-date", pattern="^-?(date|employee|flags|punch_count)$"),
               page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=200),
               scope: OnsiteScope = Depends(require_onsite_permission(Perm.EXCEPTIONS_READ)), db: Session = Depends(get_db)):
    site, tz, today_ = _site_and_day(db, scope, site_id, None)
    start, end = svc.resolve_range(date_from, date_to, default_days=7, today=today_)
    return svc.exceptions(db, scope.allowed_site_ids, site, tz, start, end, workforce_directory.load(), flag=flag, q=q,
                          page=page, page_size=page_size, emp_code=emp_code, department=department,
                          identity_class=identity_class, sort=sort, bamboohr_id=bamboohr_id)
