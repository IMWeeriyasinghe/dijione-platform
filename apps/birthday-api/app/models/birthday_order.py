from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import AddressVerificationStatus, OrderStatus
from app.db.base import Base, TimestampMixin


class BirthdayOrder(TimestampMixin, Base):
    """``id`` is the true PK (never the primary external identifier);
    ``order_reference`` is the human-readable identifier
    (``BDAY-EMP{employee_id}-{year}-{sequence}``) generated from
    ``OrderSequence``.

    Idempotency (DB-level, critical): the unique constraint on
    (employee_id, birthday_year) below is the enforcement point for
    ``create_or_get_order`` — not an in-memory check a concurrent/retried
    scan could race past. ``quantity`` is never incremented on
    re-detection.
    """

    __tablename__ = "birthday_orders"
    __table_args__ = (
        UniqueConstraint("employee_id", "birthday_year", name="uq_birthday_orders_employee_year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_reference: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # BambooHR internal record id — not assumed numeric. Remains the
    # idempotency/join key (always present, immutable) even though it is
    # NOT the business-facing Employee ID.
    employee_id: Mapped[str] = mapped_column(String(64), index=True)
    # BambooHR's `employeeNumber` field — the actual operational Employee ID
    # Dijital Team uses (e.g. "239" for Madushanka Weeriyasinghe, whose
    # BambooHR internal `id` is "366" — verified live 2026-08-14). Nullable:
    # BambooHR data proves this can be blank for some employees. This is
    # the field the UI should display as "Employee ID"; `employee_id` above
    # stays internal/secondary.
    employee_number: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    # Denormalized snapshot at detection time — historical fact must not
    # silently mutate if BambooHR data later changes.
    employee_name: Mapped[str] = mapped_column(String(255))
    employee_email: Mapped[str] = mapped_column(String(255))

    birthday_date: Mapped[date] = mapped_column(Date)
    # Occurrence year — critical for idempotency.
    birthday_year: Mapped[int] = mapped_column(Integer, index=True)

    office_location: Mapped[str] = mapped_column(String(255))

    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=0)
    lead_time_class: Mapped[str] = mapped_column(String(16), default="NORMAL")

    quantity: Mapped[int] = mapped_column(Integer, default=1)  # admin-overridable only

    status: Mapped[str] = mapped_column(String(32), default=OrderStatus.PLANNED.value)
    hold_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # P&C-manual address verification workflow (never automated, never
    # triggers employee contact) — gates supplier-actionability alongside
    # eligibility; see app/services/address_verification_service.py and
    # order_email_service.py's send gate.
    address_verification_status: Mapped[str] = mapped_column(
        String(32), default=AddressVerificationStatus.NOT_CHECKED.value
    )

    # Delivery-address snapshot (P&C-manual verification workflow) — never
    # written back to BambooHR. All nullable: unset until an order is
    # created and a BambooHR/manual value is captured. See
    # app/services/address_verification_service.py.
    delivery_address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    delivery_address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    delivery_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    delivery_state_province: Mapped[str | None] = mapped_column(String(120), nullable=True)
    delivery_postal_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    delivery_country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # "BAMBOOHR" (raw snapshot at detection time) | "MANUAL_CORRECTION"
    # (P&C edited it) — lets the UI show whether the current snapshot is
    # the original BambooHR value or a human correction.
    delivery_address_source: Mapped[str | None] = mapped_column(String(32), nullable=True)

    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("suppliers.id"), nullable=True
    )
    # Delivery date (Phase-Next §3) — admin-set, distinct from birthday_date;
    # part of the readiness check once required by config, and what the
    # supplier portal sorts/filters on.
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    catalogue_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("supplier_catalogue_items.id"), nullable=True
    )

    is_manual_override: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_admin_review: Mapped[bool] = mapped_column(Boolean, default=False)
    is_overdue: Mapped[bool] = mapped_column(Boolean, default=False)
    has_delivery_issue: Mapped[bool] = mapped_column(Boolean, default=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # No FK to `users.id` — User is owned by platform-api's own database.
    # Null when system-generated.
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)

    supplier: Mapped[Supplier | None] = relationship(back_populates="orders")  # noqa: F821
    catalogue_item: Mapped[SupplierCatalogueItem | None] = relationship()  # noqa: F821
    events: Mapped[list[OrderEvent]] = relationship(  # noqa: F821
        back_populates="order", cascade="all, delete-orphan"
    )
    communications: Mapped[list[SupplierCommunication]] = relationship(  # noqa: F821
        back_populates="order", cascade="all, delete-orphan"
    )
    special_requirements: Mapped[list[SpecialRequirement]] = relationship(  # noqa: F821
        back_populates="order", cascade="all, delete-orphan"
    )
