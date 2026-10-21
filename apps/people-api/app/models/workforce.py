from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, utcnow


class WorkforceDirectoryEntry(TimestampMixin, Base):
    """The generic Workforce Directory read model — every BambooHR employee,
    Active and Inactive (see ``docs/platform/workforce-directory.md``).

    Separate from ``Employee`` (the Birthday-oriented Employee contract,
    which holds only Active employees with a usable birthday) so neither
    contract's population can affect the other. Minimum data only: no
    birthday, address, email or compensation. Rows are never deleted — a
    record that leaves BambooHR gets ``present_in_source=False``.
    """

    __tablename__ = "workforce_directory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bamboohr_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Verbatim BambooHR employeeNumber. Nullable and NOT unique: blanks and
    # duplicates are real and are reported by consumers, never resolved here.
    employee_number: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    display_name: Mapped[str] = mapped_column(String(255), default="")
    department: Mapped[str] = mapped_column(String(255), default="")
    job_title: Mapped[str] = mapped_column(String(255), default="")
    location: Mapped[str] = mapped_column(String(255), default="")
    employment_status: Mapped[str] = mapped_column(String(32), default="", index=True)
    hire_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    termination_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    present_in_source: Mapped[bool] = mapped_column(Boolean, default=True)
    first_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkforceSyncRun(TimestampMixin, Base):
    """Durable sync-run state for the Workforce Directory (CLAUDE.md rule
    13). Same shape as ``PeopleSyncRun`` but a separate table, so workforce
    runs never appear in the Employee contract's freshness or history."""

    __tablename__ = "workforce_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(32), default="BAMBOOHR")
    trigger_type: Mapped[str] = mapped_column(String(16))
    requested_by_application: Mapped[str] = mapped_column(String(64))
    requested_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(String(16), default="QUEUED", index=True)
    records_read: Mapped[int] = mapped_column(Integer, default=0)
    records_created: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    records_unchanged: Mapped[int] = mapped_column(Integer, default=0)
    records_absent: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
