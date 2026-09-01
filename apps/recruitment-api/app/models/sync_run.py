from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, utcnow


class SyncStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


TERMINAL_STATUSES = frozenset({SyncStatus.SUCCEEDED, SyncStatus.PARTIAL, SyncStatus.FAILED})
ACTIVE_STATUSES = frozenset({SyncStatus.QUEUED, SyncStatus.RUNNING})


class SyncTriggerType(StrEnum):
    SCHEDULED = "SCHEDULED"
    AD_HOC = "AD_HOC"


class RecruitmentSyncRun(TimestampMixin, Base):
    """Durable record of one Lever reconciliation run — the DijiOne standard
    source-sync lifecycle state. Never stores provider secrets or raw
    candidate PII: counts + a safe error summary only.
    """

    __tablename__ = "recruitment_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(32), default="LEVER")
    trigger_type: Mapped[str] = mapped_column(String(16))
    requested_by_application: Mapped[str] = mapped_column(String(64))
    requested_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(String(16), default=SyncStatus.QUEUED.value, index=True)
    records_read: Mapped[int] = mapped_column(Integer, default=0)
    records_created: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    records_unchanged: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
