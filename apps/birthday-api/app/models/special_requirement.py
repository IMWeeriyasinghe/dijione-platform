from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class SpecialRequirement(TimestampMixin, Base):
    """``kind`` distinguishes SUPPLIER_INSTRUCTION (external-visible) from
    INTERNAL_NOTE (never serialized into any supplier-facing schema/email —
    enforced via genuinely separate Pydantic response schemas, not a
    runtime filter)."""

    __tablename__ = "special_requirements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("birthday_orders.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)

    # No FK to `users.id` — User is owned by platform-api's own database.
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)

    order: Mapped[BirthdayOrder] = relationship(back_populates="special_requirements")  # noqa: F821
