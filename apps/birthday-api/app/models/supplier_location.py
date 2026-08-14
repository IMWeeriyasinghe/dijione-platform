from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class SupplierLocation(TimestampMixin, Base):
    __tablename__ = "supplier_locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), index=True)
    # V1 assumes one active supplier per office (unique on office_location) —
    # a scope simplification, not a hard architectural limit.
    office_location: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)

    supplier: Mapped[Supplier] = relationship(back_populates="locations")  # noqa: F821
