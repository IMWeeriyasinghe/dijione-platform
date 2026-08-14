from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import CommunicationChannel, CommunicationStatus
from app.db.base import Base, TimestampMixin


class SupplierCommunication(TimestampMixin, Base):
    """Every email must include ``order.order_reference`` in subject and
    body — enforced in the rendering service, not left to template
    authors."""

    __tablename__ = "supplier_communications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("birthday_orders.id", ondelete="CASCADE"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    direction: Mapped[str] = mapped_column(String(16))
    channel: Mapped[str] = mapped_column(String(16), default=CommunicationChannel.EMAIL.value)
    subject: Mapped[str] = mapped_column(String(500), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Graph message id — populated by the send call, reserved for Phase E/G
    # reply-matching.
    message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=CommunicationStatus.QUEUED.value)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    order: Mapped[BirthdayOrder] = relationship(back_populates="communications")  # noqa: F821
