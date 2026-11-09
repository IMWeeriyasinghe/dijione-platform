from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, utcnow
from app.models.attendance import new_id


class NotificationOutbox(Base):
    """Written in the same transaction as the attendance change, delivered later.
    Its rows are also the record of what was sent, to whom and when."""

    __tablename__ = "notification_outbox"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING', 'SENT', 'FAILED')", name="ck_notification_outbox_status"),
        Index("ix_notification_outbox_due", "status", "next_attempt_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)
    kind: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, default="")
    link_url: Mapped[str] = mapped_column(String(500))
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    required_permissions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    exclude_user_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
