"""Reminder infrastructure models:
- AtworkReminderWatermark: single-row deploy timestamp; sessions checked in
  before this date never receive staged reminders (rollout suppression).
- AtworkReminderEmailSent: at-most-one email per (session, stage) with
  transaction-safe claiming and retry support.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, utcnow
from app.models.attendance import new_id


class AtworkReminderWatermark(Base):
    """One row (id=1). Populated at migration time; never updated after deploy."""

    __tablename__ = "atwork_reminder_watermark"
    __table_args__ = (CheckConstraint("id = 1", name="ck_atwork_reminder_watermark_single"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    watermark_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class AtworkReminderEmailSent(Base):
    """One row per (session_id, stage). Claimed with PENDING, resolved to SENT
    or FAILED. The unique constraint on (session_id, stage) ensures at-most-one
    claim even under concurrent scheduler runs (IntegrityError on the second)."""

    __tablename__ = "atwork_reminder_email_sent"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING','SENT','FAILED')", name="ck_reminder_email_status"),
        CheckConstraint("stage IN (1,2,3)", name="ck_reminder_email_stage"),
        UniqueConstraint("session_id", "stage", name="uq_reminder_email_session_stage"),
        Index("ix_reminder_email_pending", "status", "next_attempt_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    stage: Mapped[int] = mapped_column(Integer, nullable=False)
    recipient_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
