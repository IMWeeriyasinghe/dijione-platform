from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class InternalAlert(TimestampMixin, Base):
    """Outbox for internal (P&C) email alerts about supplier activity.

    One row per business event per recipient. ``source_key`` identifies the
    event (``message:<communication id>``, ``issue:<issue id>``), so the
    unique constraint makes creation idempotent: a retried sweep or a
    repeated call can never produce a second email for the same event and
    recipient. The supplier's own action is committed before any row here is
    sent, so a mail outage never loses or rolls back the supplier event.
    """

    __tablename__ = "birthday_internal_alerts"
    __table_args__ = (UniqueConstraint("source_key", "recipient", name="uq_internal_alert_source_recipient"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("birthday_orders.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(32))
    source_key: Mapped[str] = mapped_column(String(64), index=True)
    recipient: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    # Rendered HTML body, kept so a retry resends exactly the same email.
    body: Mapped[str] = mapped_column(Text, default="")
    # PENDING -> SENT | SIMULATED | BLOCKED | DISABLED | FAILED (retried) | GAVE_UP
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    transport_outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
