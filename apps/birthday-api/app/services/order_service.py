"""Idempotent order creation.

The DB-level unique constraint on (employee_id, birthday_year) — not an
in-memory existence check — is the real enforcement point: a concurrent or
retried scan attempting to insert twice must lose the race safely and
return the existing row untouched (quantity/status are never mutated on the
duplicate path).

The insert attempt runs inside a SAVEPOINT (``db.begin_nested``) so that a
caught IntegrityError only unwinds this one order's insert, not the whole
scan run's session — ``detection_service.run_daily_scan`` processes many
employees in one session/transaction and commits once at the end.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import ActorType, AddressVerificationStatus, OrderStatus, SpecialRequirementKind
from app.models.birthday_order import BirthdayOrder
from app.models.order_event import OrderEvent
from app.repositories.birthday_order_repository import BirthdayOrderRepository
from app.schemas.order import SupplierOrderView


def create_or_get_order(
    db: Session,
    *,
    employee_id: str,
    employee_number: str | None = None,
    employee_name: str,
    employee_email: str,
    order_reference: str,
    birthday_date: date,
    birthday_year: int,
    office_location: str,
    lead_time_days: int,
    lead_time_class: str,
    status: OrderStatus,
    requires_admin_review: bool,
    hold_reason: str | None,
    supplier_id: int | None,
) -> tuple[BirthdayOrder, bool]:
    repo = BirthdayOrderRepository(db)

    order = BirthdayOrder(
        order_reference=order_reference,
        employee_id=employee_id,
        employee_number=employee_number,
        employee_name=employee_name,
        employee_email=employee_email,
        birthday_date=birthday_date,
        birthday_year=birthday_year,
        office_location=office_location,
        lead_time_days=lead_time_days,
        lead_time_class=str(lead_time_class),
        status=str(status),
        hold_reason=hold_reason,
        supplier_id=supplier_id,
        requires_admin_review=requires_admin_review,
    )

    try:
        with db.begin_nested():
            db.add(order)
            db.flush()
    except IntegrityError:
        existing = repo.get_by_employee_and_year(employee_id, birthday_year)
        if existing is None:
            raise
        return existing, False

    _write_events(db, order, status, hold_reason)
    return order, True


def _write_events(db: Session, order: BirthdayOrder, status: OrderStatus, hold_reason: str | None) -> None:
    db.add(
        OrderEvent(
            order_id=order.id,
            event_type="DETECTED",
            to_status=str(status),
            actor_type=ActorType.SYSTEM.value,
        )
    )
    if status in (OrderStatus.REQUIRES_ATTENTION, OrderStatus.ON_HOLD):
        db.add(
            OrderEvent(
                order_id=order.id,
                event_type="EXCEPTION",
                to_status=str(status),
                actor_type=ActorType.SYSTEM.value,
                detail=hold_reason,
            )
        )
    db.flush()


def to_supplier_view(order: BirthdayOrder) -> SupplierOrderView:
    """Converts a BirthdayOrder into exactly what a supplier is allowed to
    see (plan §6) — fulfilment facts only, never HR eligibility, hire
    dates, or the internal eligibility machinery. Callers (the
    supplier-portal routes) are responsible for only ever calling this on
    orders already scoped to the caller's own supplier_id."""
    return SupplierOrderView(
        id=order.id,
        order_reference=order.order_reference,
        employee_name=order.employee_name,
        birthday_date=order.birthday_date,
        delivery_date=order.delivery_date,
        office_location=order.office_location,
        quantity=order.quantity,
        catalogue_item_name=order.catalogue_item.name if order.catalogue_item else None,
        address_verified=order.address_verification_status == AddressVerificationStatus.VERIFIED.value,
        status=order.status,
        special_instructions=[
            req.text
            for req in (order.special_requirements or [])
            if req.kind == SpecialRequirementKind.SUPPLIER_INSTRUCTION.value
        ],
    )
