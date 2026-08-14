"""Live-BambooHR-driven "upcoming birthdays" directory view.

Distinct from ``detection_service.run_daily_scan``: this never creates a
``BirthdayOrder`` and never mutates the database. It exists to answer "who
has a birthday coming up" for the frontend, independent of whether the
daily scan has already picked that employee up (scan windows are
configurable and can be narrower than the ``days`` window a caller asks
for here).

Active-employee filtering happens exclusively through
``BambooHRClient.list_active_employees()`` (CR: never trust a frontend
filter) — the mock/live implementation is the single source of truth for
"active" (BambooHR's ``employment_status`` field, ``"Active"`` vs
anything else, e.g. ``"Terminated"``).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.integrations.bamboohr.client import BambooHRClient, BambooHRFetchError
from app.integrations.bamboohr.mapper import map_employee
from app.repositories.birthday_order_repository import BirthdayOrderRepository
from app.schemas.birthday_directory import UpcomingBirthdayItem
from app.services.audit_service import AuditService
from app.services.detection_service import compute_next_birthday_occurrence
from app.services.eligibility_service import compute_eligibility

NOT_CREATED_STATUS = "not_created"
DEFAULT_CAKE_QUANTITY = 1  # fixed constant — no AI/dynamic quantity logic in this path

_NEEDS_ATTENTION_ORDER_STATUSES = {"REQUIRES_ATTENTION", "ON_HOLD"}
_NEEDS_ATTENTION_ADDRESS_STATUSES = {"NEEDS_UPDATE", "VERIFICATION_REQUESTED"}


def group_for(item: UpcomingBirthdayItem) -> str:
    """Server-side mirror of the frontend's ``groupFor()`` (Phase-Next §4)
    — moved here so filtering by group is a real query-time filter, not a
    client-side ``.filter()`` over an already-fetched, unpaginated list."""
    if item.eligible and (
        item.cake_order_status in _NEEDS_ATTENTION_ORDER_STATUSES
        or (item.address_verification_status or "") in _NEEDS_ATTENTION_ADDRESS_STATUSES
    ):
        return "NEEDS_ATTENTION"
    if not item.eligible:
        if item.eligibility_reason == "FUTURE_STARTER":
            return "FUTURE_STARTER"
        return "NOT_ELIGIBLE"
    return "ELIGIBLE"


_SORT_KEYS = {
    "days_until_birthday": lambda i: i.days_until_birthday,
    "hire_date": lambda i: i.hire_date or "",
    "employee_name": lambda i: i.display_name.lower(),
    "employee_number": lambda i: i.employee_number or "",
}


def list_upcoming_birthdays(
    db: Session,
    bamboohr_client: BambooHRClient,
    *,
    days: int,
    today: date | None = None,
    audit_service: AuditService | None = None,
    search: str | None = None,
    group_filter: str | None = None,
    sort_by: str | None = None,
    sort_direction: str = "asc",
) -> list[UpcomingBirthdayItem]:
    """Returns active employees whose next birthday occurrence falls within
    ``[today, today + days]`` inclusive, sorted soonest-first.

    Year-boundary birthdays (e.g. today is late December, employee's
    birthday is Jan 3) are handled correctly because
    ``compute_next_birthday_occurrence`` always returns the *next*
    occurrence on or after ``today`` — rolling into next year when the
    month/day has already passed this year — so ``days_until_birthday`` is
    always a small non-negative number, never a large "days since last
    January" value.
    """
    today = today or datetime.now(UTC).date()
    audit_service = audit_service or AuditService()
    repo = BirthdayOrderRepository(db)

    try:
        raw_employees = bamboohr_client.list_active_employees()
    except Exception as exc:  # noqa: BLE001 - provider failure must not crash the request
        audit_service.log(
            actor_id=None,
            action="birthday.bamboohr_fetch_failed",
            entity_type="birthday_integration",
            entity_id=0,
            metadata={"error_type": type(exc).__name__},  # no PII: no employee data included
        )
        raise BambooHRFetchError("Failed to fetch employee directory from BambooHR") from exc

    items: list[UpcomingBirthdayItem] = []
    for raw_employee in raw_employees:
        try:
            employee = map_employee(raw_employee)
            birth_month = employee["birth_month"]
            birth_day = employee["birth_day"]
            if not isinstance(birth_month, int) or not isinstance(birth_day, int):
                raise ValueError("birth_month/birth_day missing or malformed")

            occurrence_date, occurrence_year = compute_next_birthday_occurrence(
                birth_month, birth_day, today
            )
            days_until = (occurrence_date - today).days
            if days_until > days:
                continue

            order = repo.get_by_employee_and_year(employee["employee_id"], occurrence_year)
            cake_order_status = order.status if order is not None else NOT_CREATED_STATUS

            eligible, reason = compute_eligibility(
                employment_status=employee["employment_status"],
                hire_date=employee.get("hire_date"),
                termination_date=employee.get("termination_date"),
                birth_month=birth_month,
                birth_day=birth_day,
                occurrence_date=occurrence_date,
            )

            items.append(
                UpcomingBirthdayItem(
                    employee_id=employee["employee_id"],
                    employee_number=employee.get("employee_number"),
                    display_name=employee["full_name"],
                    birthday=f"{birth_month:02d}-{birth_day:02d}",
                    days_until_birthday=days_until,
                    department=employee.get("department") or "",
                    location=employee["office_location"],
                    cake_order_status=cake_order_status,
                    hire_date=employee["hire_date"].isoformat() if employee.get("hire_date") else None,
                    eligible=eligible,
                    eligibility_reason=reason.value,
                    address_verification_status=order.address_verification_status if order is not None else None,
                )
            )
        except Exception as exc:  # noqa: BLE001 - one malformed record must not break the list
            audit_service.log(
                actor_id=None,
                action="birthday.bamboohr_record_skipped",
                entity_type="birthday_integration",
                entity_id=0,
                metadata={"error_type": type(exc).__name__},  # no PII
            )
            continue

    if group_filter and group_filter != "ALL":
        items = [i for i in items if group_for(i) == group_filter]

    if search:
        needle = search.strip().lower()
        items = [
            i for i in items
            if needle in i.display_name.lower()
            or needle in (i.employee_number or "").lower()
            or needle in i.employee_id.lower()
        ]

    sort_key = _SORT_KEYS.get(sort_by or "", _SORT_KEYS["days_until_birthday"])
    items.sort(key=sort_key, reverse=(sort_direction == "desc"))
    return items
