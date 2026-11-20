"""Platform-owned email notification state (DijiOne access notifications).

- ``EmailOutbox``: one row per email, written in the same transaction as the access change
  that caused it, dispatched later. Rows are kept: the table is also the delivery history.
- ``UserAccessSnapshot``: the effective access each person was last notified about, the
  baseline the next change is compared with.
- ``NotificationEventSetting``: per-event on/off switch (Admin > Notifications).
- ``EmailTestRecipient``: the DEV/UAT recipient allowlist (ignored in production).

Platform-api's own tables in ``platform_*``; no other service reads them.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, utcnow


class OutboxStatus:
    PENDING = "PENDING"  # waiting for its first (or next) attempt
    SENDING = "SENDING"  # claimed by a dispatcher
    RETRY = "RETRY"  # a transport attempt failed; another is scheduled
    SUBMITTED = "SUBMITTED"  # Microsoft Graph accepted it (202). Not a delivery confirmation.
    SIMULATED = "SIMULATED"  # null transport: nothing left the system
    FAILED = "FAILED"  # retries exhausted
    BLOCKED = "BLOCKED"  # recipient not on the DEV/UAT allowlist
    DISABLED = "DISABLED"  # sending is disabled in this environment
    SUPERSEDED = "SUPERSEDED"  # replaced by a later email covering the same change
    SKIPPED = "SKIPPED"  # event switched off before it was sent

    DISPATCHABLE = (PENDING, RETRY)
    TERMINAL = (SUBMITTED, SIMULATED, FAILED, BLOCKED, DISABLED, SUPERSEDED, SKIPPED)
    RETRYABLE_BY_ADMIN = (FAILED, BLOCKED, DISABLED, SKIPPED)
    ALL = (PENDING, SENDING, RETRY, SUBMITTED, SIMULATED, FAILED, BLOCKED, DISABLED, SUPERSEDED, SKIPPED)


class EmailOutbox(TimestampMixin, Base):
    __tablename__ = "email_outbox"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_email_outbox_dedupe_key"),
        UniqueConstraint("correlation_id", name="uq_email_outbox_correlation_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    correlation_id: Mapped[str] = mapped_column(String(36))
    application_key: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    recipient_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    recipient_email: Mapped[str] = mapped_column(String(255), index=True)
    subject: Mapped[str] = mapped_column(String(255))
    template_key: Mapped[str] = mapped_column(String(64))
    # Only what the template needs (application names, change kinds): no permissions detail.
    template_data: Mapped[dict] = mapped_column(JSON, default=dict)
    # Access notifications: the access the person had before this email's change, so a quick
    # follow-up change can be folded into one email (see access_notifications.enqueue).
    from_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default=OutboxStatus.PENDING, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    not_before: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transport_outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)
    graph_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    superseded_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class UserAccessSnapshot(Base):
    __tablename__ = "user_access_snapshots"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    # {"active": bool, "apps": {module_key: [permission, ...]}}
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=0)
    welcomed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class NotificationEventSetting(Base):
    __tablename__ = "notification_event_settings"

    event_type: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class EmailTestRecipient(TimestampMixin, Base):
    __tablename__ = "email_test_recipients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # An exact address, or "@domain" for a whole domain.
    address: Mapped[str] = mapped_column(String(255), unique=True)
    label: Mapped[str] = mapped_column(String(255), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str] = mapped_column(Text, default="")
