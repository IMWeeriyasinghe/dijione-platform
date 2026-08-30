from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class SupplierCatalogueItem(TimestampMixin, Base):
    """Kept intentionally lightweight for V1 — no pricing/SKU catalogue,
    only what "supplier can be asked for" needs (§4)."""

    __tablename__ = "supplier_catalogue_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # The supplier's default cake — detection auto-applies this to every
    # new order for the supplier (plan §31/§L). At most one per supplier;
    # enforced in app/api/routes/suppliers.py, not at the DB level (V1).
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    supplier: Mapped[Supplier] = relationship(back_populates="catalogue_items")  # noqa: F821
