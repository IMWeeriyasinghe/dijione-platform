from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import CommunicationChannel, CommunicationStatus
from app.db.base import Base, TimestampMixin


class SupplierCommunication(TimestampMixin, Base):
    """The canonical per-order conversation record — every message either
    party sent, on either channel, either direction (Phase 1 §G). One
    store, one Unified Timeline; there is deliberately no separate
    ``order_message`` table.

    ``channel`` ∈ EMAIL | PORTAL | SYSTEM (TEAMS reserved). ``direction`` is
    relative to the supplier: OUTBOUND = to supplier, INBOUND = from
    supplier. Every email must include ``order.order_reference`` in subject
    and body — enforced in the rendering service.
    """

    __tablename__ = "supplier_communications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("birthday_orders.id", ondelete="CASCADE"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    direction: Mapped[str] = mapped_column(String(16))
    channel: Mapped[str] = mapped_column(String(16), default=CommunicationChannel.EMAIL.value)
    # USER | SUPPLIER | SYSTEM + the id of that actor (platform user id or
    # supplier_user id). Nullable for legacy/system rows.
    author_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    author_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subject: Mapped[str] = mapped_column(String(500), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Provider (Graph) message id — set on outbound send and inbound ingest;
    # inbound dedupe is keyed on it. ``in_reply_to`` carries the outbound
    # message_id a supplier email reply threads to.
    message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    in_reply_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=CommunicationStatus.QUEUED.value)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    # Outbound-email auto-retry (Phase 1 §1.3): next attempt time + ceiling.
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # When this message belongs to a structured concern thread.
    issue_id: Mapped[int | None] = mapped_column(
        ForeignKey("order_issues.id", ondelete="SET NULL"), nullable=True, index=True
    )

    order: Mapped[BirthdayOrder] = relationship(back_populates="communications")  # noqa: F821
