from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UTCDateTime, utcnow
from app.models.attendance import new_id

_PENDING_SESSION = text("status = 'PENDING' AND session_id IS NOT NULL")


class AttendanceEmployee(Base):
    """Display name snapshot taken from verified claims, so Management screens
    can name people. Not an identity or role record: Platform Core owns those."""

    __tablename__ = "attendance_employees"

    platform_user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    __mapper_args__ = {"version_id_col": version}


class CorrectionRequest(TimestampMixin, Base):
    """An employee's proposal. Official records change only when it is approved."""

    __tablename__ = "correction_requests"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING', 'APPROVED', 'REJECTED', 'WITHDRAWN')", name="ck_correction_requests_status"),
        CheckConstraint("kind IN ('AMEND', 'CREATE_MISSING')", name="ck_correction_requests_kind"),
        UniqueConstraint("platform_user_id", "client_request_id", name="uq_correction_requests_client_request"),
        Index(
            "uq_correction_requests_one_pending",
            "session_id",
            unique=True,
            sqlite_where=_PENDING_SESSION,
            postgresql_where=_PENDING_SESSION,
        ),
        Index("ix_correction_requests_user", "platform_user_id", "created_at"),
        Index("ix_correction_requests_status", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    platform_user_id: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    session_id: Mapped[str | None] = mapped_column(ForeignKey("attendance_sessions.id", ondelete="RESTRICT"), nullable=True)
    base_session_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    original: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    proposed: Mapped[dict] = mapped_column(JSON)
    client_request_id: Mapped[str] = mapped_column(String(64))
    reviewer_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    __mapper_args__ = {"version_id_col": version}


class AtworkSettings(Base):
    """DijiAtWork's local operational policy: one row, id 1."""

    __tablename__ = "atwork_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_atwork_settings_single_row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    enabled_work_modes: Mapped[list] = mapped_column(JSON)
    business_time_zone: Mapped[str] = mapped_column(String(64))
    missed_checkout_hours: Mapped[int] = mapped_column(Integer)
    time_format: Mapped[str] = mapped_column(String(8))
    default_history_days: Mapped[int] = mapped_column(Integer)
    updated_by_user_id: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    __mapper_args__ = {"version_id_col": version}
