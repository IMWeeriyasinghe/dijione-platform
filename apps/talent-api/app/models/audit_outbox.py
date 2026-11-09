from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow

PENDING = "PENDING"
DELIVERED = "DELIVERED"
# Platform Core refused the event for good; kept for a person to review.
FAILED = "FAILED"


class AuditOutbox(Base):
    """An audit event saved with the change it records, awaiting delivery to
    Platform Core. ``event_id`` stays the same on every delivery attempt."""

    __tablename__ = "audit_outbox"
    __table_args__ = (Index("ix_audit_outbox_status_next_attempt", "status", "next_attempt_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True)
    payload: Mapped[str] = mapped_column(Text)  # JSON body of the audit event
    status: Mapped[str] = mapped_column(String(16), default=PENDING)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # A claim expires, so a worker that dies cannot strand its batch.
    claimed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(64), nullable=True)  # a status or exception name only
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
