from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Supplier(TimestampMixin, Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")

    primary_contact_name: Mapped[str] = mapped_column(String(255), default="")
    primary_contact_email: Mapped[str] = mapped_column(String(255), default="")
    primary_contact_phone: Mapped[str] = mapped_column(String(64), default="")
    escalation_contact_name: Mapped[str] = mapped_column(String(255), default="")
    escalation_contact_email: Mapped[str] = mapped_column(String(255), default="")

    lead_time_days: Mapped[int] = mapped_column(Integer, default=0)
    working_days: Mapped[str] = mapped_column(String(255), default="")
    cutoff_time: Mapped[str] = mapped_column(String(32), default="")
    notes: Mapped[str] = mapped_column(Text, default="")  # internal-only, never supplier-visible

    # Island-wide / catch-all supplier: when detection cannot resolve a
    # supplier from the team member's office location, the single supplier
    # flagged is_default (if any, and ACTIVE) is used instead. At most one
    # supplier may hold this flag — the create/update routes clear it on
    # every other row when it is set.
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    locations: Mapped[list[SupplierLocation]] = relationship(  # noqa: F821
        back_populates="supplier", cascade="all, delete-orphan"
    )
    catalogue_items: Mapped[list[SupplierCatalogueItem]] = relationship(  # noqa: F821
        back_populates="supplier", cascade="all, delete-orphan"
    )
    users: Mapped[list[SupplierUser]] = relationship(  # noqa: F821
        back_populates="supplier", cascade="all, delete-orphan"
    )
    orders: Mapped[list[BirthdayOrder]] = relationship(back_populates="supplier")  # noqa: F821
