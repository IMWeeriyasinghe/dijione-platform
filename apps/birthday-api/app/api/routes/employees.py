"""Live-People-source "upcoming birthdays" directory endpoint — read-only,
never creates orders. See ``app/services/directory_service.py`` for the
active-employee-filtering and year-boundary-safe date logic."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import BirthdayScope, require_birthday_permission
from app.db.session import get_db
from app.integrations.factory import get_employee_source
from app.integrations.people_source.client import (
    EmployeeSourceFetchError,
    EmployeeSourceUnavailableError,
)
from app.schemas.birthday_directory import UpcomingBirthdaysResponse
from app.services.audit_service import AuditService
from app.services.directory_service import list_upcoming_birthdays

router = APIRouter(prefix="/api/birthday/employees", tags=["birthday-employees"])
people_router = APIRouter(prefix="/api/birthday/people", tags=["birthday-people"])


@people_router.get("/freshness")
def people_freshness(
    db: Session = Depends(get_db),
    _scope: BirthdayScope = Depends(require_birthday_permission("birthday.dashboard.read")),
) -> dict:
    """Team-member data freshness (Phase 1.5 §B). Auto-refreshed daily by
    ``people-sync-job``; this backs the "last refreshed / Refresh now"
    display. Best-effort — people-api down returns available:false, not a 5xx."""
    src = get_employee_source()
    if not hasattr(src, "freshness"):
        return {"available": False, "auto_refresh": "daily", "reason": "People integration is in mock mode"}
    try:
        f = src.freshness()
    except EmployeeSourceUnavailableError:
        return {"available": False, "auto_refresh": "daily", "reason": "People service unavailable"}
    return {"available": True, "auto_refresh": "daily", **f}


@people_router.post("/refresh", status_code=202)
def people_refresh(
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.config.manage")),
) -> dict:
    """Ad-hoc team-member data refresh from BambooHR (via people-api). The
    daily job is the default; this is the manual override."""
    src = get_employee_source()
    if not hasattr(src, "request_sync"):
        raise HTTPException(status.HTTP_409_CONFLICT, "People integration is in mock mode — nothing to refresh")
    try:
        result = src.request_sync(requested_by_user_id=scope.user.id)
    except EmployeeSourceUnavailableError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "People service unavailable") from exc
    try:
        AuditService().log(
            actor_id=scope.user.id, action="birthday.people.manual_refresh",
            entity_type="people", entity_id=0, new_state=result,
        )
    except Exception:  # noqa: BLE001
        pass
    return result


@router.get("/upcoming-birthdays", response_model=UpcomingBirthdaysResponse)
def get_upcoming_birthdays(
    days: int = 30,
    search: str | None = None,
    filter: str | None = None,  # noqa: A002 - matches the documented API parameter name
    cake_status_filter: str | None = None,
    province: str | None = None,
    sort_by: str | None = None,
    sort_direction: str = "asc",
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    _scope: BirthdayScope = Depends(require_birthday_permission("birthday.dashboard.read")),
) -> UpcomingBirthdaysResponse:
    if days < 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "days must be non-negative")
    if sort_direction not in ("asc", "desc"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "sort_direction must be 'asc' or 'desc'")
    page = max(page, 1)
    page_size = max(1, min(page_size, 500))

    client = get_employee_source()
    try:
        birthdays = list_upcoming_birthdays(
            db, client, days=days, search=search, group_filter=filter,
            cake_status_filter=cake_status_filter, province=province,
            sort_by=sort_by, sort_direction=sort_direction,
        )
    except EmployeeSourceFetchError as exc:
        # Degraded state (Architecture Completion Plan Wave E): people-api
        # unreachable — the staff directory view shows unavailable rather
        # than a stale/misleading list.
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Employee directory temporarily unavailable"
        ) from exc

    total = len(birthdays)
    start = (page - 1) * page_size
    page_items = birthdays[start : start + page_size]

    return UpcomingBirthdaysResponse(days=days, birthdays=page_items, total=total, page=page, page_size=page_size)
