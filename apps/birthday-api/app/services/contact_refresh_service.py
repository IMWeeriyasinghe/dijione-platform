"""Explicit, per-order "Refresh contact from People" for legacy orders.

Birthday snapshots employee data when an order is created, so an order
created before phone snapshotting existed keeps empty contact fields even
though People now holds the number. This fills ONLY the empty snapshot
fields from People (never BambooHR directly), only on an order that has not
been released. It never overwrites a non-empty value or a chosen delivery
contact, never touches the address, verification, status, greeting or
release, and never sends an email. Audit text carries field names only —
never a phone number.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.constants import ActorType
from app.integrations.factory import get_employee_source
from app.integrations.people_source.client import EmployeeSourceUnavailableError
from app.models.birthday_order import BirthdayOrder
from app.models.order_event import OrderEvent

EVENT_TYPE = "EMPLOYEE_CONTACT_REFRESHED"


class ContactRefreshError(Exception):
    """Non-destructive refusal; ``code`` is stable for the API/UI."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class ContactRefreshResult:
    order: BirthdayOrder
    fields_populated: list[str] = field(default_factory=list)


def _blank(value: str | None) -> bool:
    return not (value or "").strip()


def is_refreshable(order: BirthdayOrder) -> bool:
    """Unreleased, identifiable, and at least one contact snapshot empty."""
    return (
        order.released_at is None
        and not _blank(order.employee_id)
        and (_blank(order.employee_mobile_phone) or _blank(order.employee_home_phone))
    )


def refresh_contact(
    db: Session, order: BirthdayOrder, *, actor_id: int | None, actor_display_name: str | None = None
) -> ContactRefreshResult:
    if order.released_at is not None:
        raise ContactRefreshError(
            "ALREADY_RELEASED", "This order has been released to the supplier; its contact cannot be refreshed."
        )
    if _blank(order.employee_id):
        raise ContactRefreshError("NO_EMPLOYEE_IDENTITY", "This order has no employee identity to look up.")
    if not (_blank(order.employee_mobile_phone) or _blank(order.employee_home_phone)):
        raise ContactRefreshError("NOTHING_TO_REFRESH", "Both contact numbers are already captured.")

    try:
        employee = get_employee_source().get_employee(order.employee_id)
    except EmployeeSourceUnavailableError as exc:
        raise ContactRefreshError("PEOPLE_UNAVAILABLE", "People is unavailable right now. Try again shortly.") from exc
    if employee is None:
        raise ContactRefreshError("EMPLOYEE_NOT_FOUND", "The employee could not be found in People.")

    mobile = (employee.mobile_phone or "").strip() or None
    home = (employee.home_phone or "").strip() or None
    if not mobile and not home:
        raise ContactRefreshError("NO_PHONE", "No contact number is currently available from People.")

    populated: list[str] = []
    if _blank(order.employee_mobile_phone) and mobile:
        order.employee_mobile_phone = mobile
        populated.append("employee_mobile_phone")
    if _blank(order.employee_home_phone) and home:
        order.employee_home_phone = home
        populated.append("employee_home_phone")
    # The supplier contact defaults only when P&C has not chosen one.
    if _blank(order.delivery_contact_phone):
        default = (order.employee_mobile_phone or "").strip() or (order.employee_home_phone or "").strip()
        if default:
            order.delivery_contact_phone = default
            populated.append("delivery_contact_phone")

    if not populated:
        raise ContactRefreshError("NO_PHONE", "No contact number is currently available from People.")

    db.add(
        OrderEvent(
            order_id=order.id,
            event_type=EVENT_TYPE,
            actor_id=actor_id,
            actor_type=ActorType.USER.value,
            actor_display_name=actor_display_name,
            detail="Contact refreshed from People: " + ", ".join(populated),
        )
    )
    db.commit()
    db.refresh(order)
    return ContactRefreshResult(order=order, fields_populated=populated)
