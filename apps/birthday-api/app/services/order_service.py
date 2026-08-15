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
    delivery_address_line1: str | None = None,
    delivery_address_line2: str | None = None,
    delivery_city: str | None = None,
    delivery_state_province: str | None = None,
    delivery_postal_code: str | None = None,
    delivery_country: str | None = None,
) -> tuple[BirthdayOrder, bool]:
    repo = BirthdayOrderRepository(db)

    # Address snapshot at detection time (plan §3E) — only marked as a
    # BambooHR-sourced snapshot when at least one field was actually
    # supplied, so a bare/no-address BambooHR record doesn't falsely claim
    # a "BAMBOOHR" source with nothing behind it.
    has_address = any(
        [delivery_address_line1, delivery_address_line2, delivery_city, delivery_state_province, delivery_postal_code, delivery_country]
    )

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
        delivery_address_line1=delivery_address_line1,
        delivery_address_line2=delivery_address_line2,
        delivery_city=delivery_city,
        delivery_state_province=delivery_state_province,
        delivery_postal_code=delivery_postal_code,
        delivery_country=delivery_country,
        delivery_address_source="BAMBOOHR" if has_address else None,
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
    is_verified = order.address_verification_status == AddressVerificationStatus.VERIFIED.value
    return SupplierOrderView(
        id=order.id,
        order_reference=order.order_reference,
        employee_name=order.employee_name,
        birthday_date=order.birthday_date,
        delivery_date=order.delivery_date,
        office_location=order.office_location,
        quantity=order.quantity,
        catalogue_item_name=order.catalogue_item.name if order.catalogue_item else None,
        address_verified=is_verified,
        # Delivery address fields are only ever populated here once
        # VERIFIED (plan §3F/H) — an unverified snapshot must never reach a
        # supplier, even if the fields exist on the order.
        delivery_address_line1=order.delivery_address_line1 if is_verified else None,
        delivery_address_line2=order.delivery_address_line2 if is_verified else None,
        delivery_city=order.delivery_city if is_verified else None,
        delivery_state_province=order.delivery_state_province if is_verified else None,
        delivery_postal_code=order.delivery_postal_code if is_verified else None,
        delivery_country=order.delivery_country if is_verified else None,
        status=order.status,
        special_instructions=[
            req.text
            for req in (order.special_requirements or [])
            if req.kind == SpecialRequirementKind.SUPPLIER_INSTRUCTION.value
        ],
    )
