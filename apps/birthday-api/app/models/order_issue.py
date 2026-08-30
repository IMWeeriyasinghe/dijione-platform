from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import OrderIssueStatus
from app.db.base import Base, TimestampMixin


class OrderIssue(TimestampMixin, Base):
    """Structured supplier/internal problem report (plan §U) — replaces
    the old fire-and-forget SUPPLIER_ISSUE-event-only signal with a real
    system of record: typed, resolvable, with a response. A matching
    OrderEvent is still written alongside creation so the order-detail
    timeline shows it inline with everything else."""

    __tablename__ = "order_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("birthday_orders.id", ondelete="CASCADE"), index=True)
    raised_by_type: Mapped[str] = mapped_column(String(16))  # SUPPLIER | USER
    raised_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    type: Mapped[str] = mapped_column(String(32))  # OrderIssueType
    detail: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default=OrderIssueStatus.OPEN.value)
    resolution_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    order: Mapped[BirthdayOrder] = relationship(back_populates="issues")  # noqa: F821
