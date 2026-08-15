"""Live-BambooHR "upcoming birthdays" directory endpoint — read-only, never
creates orders. See ``app/services/directory_service.py`` for the
active-employee-filtering and year-boundary-safe date logic."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import BirthdayScope, require_birthday_permission
from app.db.session import get_db
from app.integrations.bamboohr.client import BambooHRFetchError
from app.integrations.factory import get_bamboohr_client
from app.schemas.birthday_directory import UpcomingBirthdaysResponse
from app.services.directory_service import list_upcoming_birthdays

router = APIRouter(prefix="/api/birthday/employees", tags=["birthday-employees"])


@router.get("/upcoming-birthdays", response_model=UpcomingBirthdaysResponse)
def get_upcoming_birthdays(
    days: int = 30,
    search: str | None = None,
    filter: str | None = None,  # noqa: A002 - matches the documented API parameter name
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

    client = get_bamboohr_client()
    try:
        birthdays = list_upcoming_birthdays(
            db, client, days=days, search=search, group_filter=filter, province=province,
            sort_by=sort_by, sort_direction=sort_direction,
        )
    except BambooHRFetchError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Unable to reach the employee directory (BambooHR)"
        ) from exc

    total = len(birthdays)
    start = (page - 1) * page_size
    page_items = birthdays[start : start + page_size]

    return UpcomingBirthdaysResponse(days=days, birthdays=page_items, total=total, page=page, page_size=page_size)
