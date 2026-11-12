"""The On-site-owned database (``onsite_<env>``): a verbatim mirror of the
Azure SQL ``onsite`` source plus DijiOne-owned site settings and sync state.

Raw source columns are copied exactly as read — never rewritten. Columns
named ``site_local_date``, ``tz_consistent``, ``sync_run_id`` and
``mirrored_at`` are the only derived/mirror metadata. ``punch_state`` keeps
the raw source value (e.g. ``"255"``) and is never interpreted as IN/OUT.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, utcnow


class SourceSite(TimestampMixin, Base):
    """Mirror of the source Sites table (safe columns only — never the API key hash)."""

    __tablename__ = "source_sites"

    site_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    time_zone: Mapped[str] = mapped_column(String(64), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_utc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SiteSettings(TimestampMixin, Base):
    """DijiOne-owned site settings. A newly discovered site is DISABLED until
    an ONSITE_ADMIN enables it (fail closed)."""

    __tablename__ = "site_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Comma-separated Workforce Directory ``location`` values that define the
    # expected population for "No activity recorded". Empty = not configured.
    expected_location_values: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AttendanceEvent(Base):
    """Verbatim mirror of the source AttendanceEvents table."""

    __tablename__ = "attendance_events"
    __table_args__ = (
        UniqueConstraint("site_id", "source_epoch", "source_transaction_id", name="uq_attendance_source"),
        Index("ix_attendance_site_date_emp", "site_id", "site_local_date", "emp_code"),
        Index("ix_attendance_emp_time", "emp_code", "punch_time_utc"),
        Index("ix_attendance_site_time", "site_id", "punch_time_utc"),
        Index("ix_attendance_received", "received_utc"),
    )

    event_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    site_id: Mapped[str] = mapped_column(String(64))
    source_epoch: Mapped[int] = mapped_column(Integer)
    source_transaction_id: Mapped[int] = mapped_column(BigInteger)
    emp_code: Mapped[str] = mapped_column(String(20))
    emp_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Raw ISO-8601 text with offset, exactly as the source datetimeoffset.
    punch_time_local: Mapped[str] = mapped_column(String(40))
    punch_time_utc: Mapped[datetime] = mapped_column(DateTime)
    time_zone: Mapped[str] = mapped_column(String(64))
    punch_state: Mapped[str | None] = mapped_column(String(5), nullable=True)
    verify_type: Mapped[int | None] = mapped_column(Integer, nullable=True)
    work_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    terminal_sn: Mapped[str | None] = mapped_column(String(50), nullable=True)
    terminal_alias: Mapped[str | None] = mapped_column(String(50), nullable=True)
    area_alias: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_attendance: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    upload_time_utc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    captured_at_utc: Mapped[datetime] = mapped_column(DateTime)
    received_utc: Mapped[datetime] = mapped_column(DateTime)
    batch_id: Mapped[str] = mapped_column(String(40))
    record_hash: Mapped[str] = mapped_column(String(80))

    # --- derived / mirror metadata (never source values) ---
    site_local_date: Mapped[date] = mapped_column(Date)
    tz_consistent: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sync_run_id: Mapped[str] = mapped_column(String(36))
    mirrored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentStatus(Base):
    """Latest snapshot of the source AgentStatus table per site (replaced each sync)."""

    __tablename__ = "agent_status"

    site_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_instance_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    health: Mapped[str] = mapped_column(String(20), default="")
    health_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_epoch: Mapped[int] = mapped_column(Integer, default=0)
    high_water_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    last_source_poll_utc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_delivery_utc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pending_count: Mapped[int] = mapped_column(Integer, default=0)
    dead_letter_count: Mapped[int] = mapped_column(Integer, default=0)
    oldest_pending_age_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_heartbeat_utc: Mapped[datetime] = mapped_column(DateTime)
    heartbeat_count: Mapped[int] = mapped_column(BigInteger, default=0)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OnsiteSyncRun(TimestampMixin, Base):
    """Durable mirror-sync run state (CLAUDE.md rule 13)."""

    __tablename__ = "onsite_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    trigger_type: Mapped[str] = mapped_column(String(16))
    requested_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="QUEUED", index=True)
    source_unavailable: Mapped[bool] = mapped_column(Boolean, default=False)
    events_read: Mapped[int] = mapped_column(Integer, default=0)
    events_inserted: Mapped[int] = mapped_column(Integer, default=0)
    events_existing: Mapped[int] = mapped_column(Integer, default=0)
    sites_discovered: Mapped[int] = mapped_column(Integer, default=0)
    high_water_received_utc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reconciliation_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class SyncState(Base):
    """Single-row high-water mark for the incremental mirror."""

    __tablename__ = "sync_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    high_water_received_utc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
