from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint, event, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import WORK_MODES
from app.db.base import Base, TimestampMixin, UTCDateTime, utcnow

if TYPE_CHECKING:
    from app.models.corrections import CorrectionRequest

_MODES_SQL = ", ".join(f"'{mode}'" for mode in WORK_MODES)
_OPEN = text("status = 'OPEN'")
_OPEN_BREAK = text("ended_at IS NULL AND voided_at IS NULL")
_HAS_CHECKOUT_KEY = text("check_out_request_id IS NOT NULL")
_HAS_END_KEY = text("end_request_id IS NOT NULL")


def new_id() -> str:
    return str(uuid.uuid4())


class AttendanceSession(TimestampMixin, Base):
    """One employee-declared working session. ``platform_user_id`` is the
    verified DijiOne user id; there is deliberately no cross-database key."""

    __tablename__ = "attendance_sessions"
    __table_args__ = (
        CheckConstraint(f"work_mode IN ({_MODES_SQL})", name="ck_attendance_sessions_work_mode"),
        CheckConstraint("status IN ('OPEN', 'COMPLETED')", name="ck_attendance_sessions_status"),
        CheckConstraint("check_out_at IS NULL OR check_out_at >= check_in_at", name="ck_attendance_sessions_order"),
        CheckConstraint("status <> 'OPEN' OR check_out_at IS NULL", name="ck_attendance_sessions_open_no_checkout"),
        CheckConstraint("status <> 'COMPLETED' OR check_out_at IS NOT NULL", name="ck_attendance_sessions_completed_checkout"),
        UniqueConstraint("platform_user_id", "check_in_request_id", name="uq_attendance_sessions_check_in_request"),
        Index("uq_attendance_sessions_one_open", "platform_user_id", unique=True, sqlite_where=_OPEN, postgresql_where=_OPEN),
        Index(
            "uq_attendance_sessions_check_out_request",
            "platform_user_id",
            "check_out_request_id",
            unique=True,
            sqlite_where=_HAS_CHECKOUT_KEY,
            postgresql_where=_HAS_CHECKOUT_KEY,
        ),
        Index("ix_attendance_sessions_user_check_in", "platform_user_id", "check_in_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    platform_user_id: Mapped[int] = mapped_column(Integer)
    work_mode: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    check_in_at: Mapped[datetime] = mapped_column(UTCDateTime())
    check_out_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    time_zone: Mapped[str] = mapped_column(String(64))
    check_in_request_id: Mapped[str] = mapped_column(String(64))
    check_out_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(Integer)
    updated_by_user_id: Mapped[int] = mapped_column(Integer)
    origin: Mapped[str] = mapped_column(String(16), default="RECORDED", server_default="RECORDED")
    correction_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    __mapper_args__ = {"version_id_col": version}

    # Official breaks only: a break replaced by an approved correction stays
    # in the table, voided, so the original record is preserved.
    breaks: Mapped[list[AttendanceBreak]] = relationship(
        back_populates="session",
        primaryjoin="and_(AttendanceSession.id == foreign(AttendanceBreak.session_id), AttendanceBreak.voided_at.is_(None))",
        order_by="AttendanceBreak.started_at",
        lazy="selectin",
    )

    approved_corrections: Mapped[list[CorrectionRequest]] = relationship(
        primaryjoin="and_(AttendanceSession.id == foreign(CorrectionRequest.session_id), CorrectionRequest.status == 'APPROVED')",
        viewonly=True,
        lazy="selectin",
    )

    @property
    def times_confirmed(self) -> bool:
        """Management approved this session's recorded times, not just its work mode."""
        return any(approval_confirms_times(c.original, c.proposed) for c in self.approved_corrections)


def approval_confirms_times(original: dict | None, proposed: dict) -> bool:
    """True when an approved correction created the session, changed its times, or
    confirmed it unchanged. A correction that changed only the work mode does not."""
    if original is None:
        return True
    times = ("check_in_at", "check_out_at", "breaks")
    if any(original.get(k) != proposed.get(k) for k in times):
        return True
    return all(original.get(k) == v for k, v in proposed.items())


class AttendanceBreak(TimestampMixin, Base):
    __tablename__ = "attendance_breaks"
    __table_args__ = (
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="ck_attendance_breaks_order"),
        UniqueConstraint("session_id", "start_request_id", name="uq_attendance_breaks_start_request"),
        Index("uq_attendance_breaks_one_open", "session_id", unique=True, sqlite_where=_OPEN_BREAK, postgresql_where=_OPEN_BREAK),
        Index(
            "uq_attendance_breaks_end_request",
            "session_id",
            "end_request_id",
            unique=True,
            sqlite_where=_HAS_END_KEY,
            postgresql_where=_HAS_END_KEY,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("attendance_sessions.id", ondelete="RESTRICT"))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime())
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    start_request_id: Mapped[str] = mapped_column(String(64))
    end_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    voided_by_correction_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    session: Mapped[AttendanceSession] = relationship(back_populates="breaks")


class AttendanceEvent(Base):
    """Append-only audit trail, written in the same transaction as the change."""

    __tablename__ = "attendance_events"
    __table_args__ = (
        Index("ix_attendance_events_session", "session_id", "occurred_at"),
        Index("ix_attendance_events_subject", "subject_user_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_user_id: Mapped[int] = mapped_column(Integer)
    subject_user_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(32))
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(36))
    session_id: Mapped[str | None] = mapped_column(ForeignKey("attendance_sessions.id", ondelete="RESTRICT"), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    before_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


def _reject_change(_mapper, _connection, _target) -> None:
    raise ValueError("Attendance events are append-only")


event.listen(AttendanceEvent, "before_update", _reject_change)
event.listen(AttendanceEvent, "before_delete", _reject_change)
