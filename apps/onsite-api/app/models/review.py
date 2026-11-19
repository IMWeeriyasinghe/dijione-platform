"""Attendance review cases (v0.9) — DijiOne-owned administrative records.

One case per identity-day: ``(site_id, local_date, identity_key)`` where
``identity_key`` is ``P:<bamboohr_id>`` (a verified team member) or
``C:<zk_emp_code>`` (a raw unmapped / conflict ZKBioTime ID). A case is
NEVER re-keyed and never touches ``attendance_events`` or identity mappings.

Four concepts are stored separately and never merged:

* Observed  — ``facts_snapshot`` (recorded fingerprints at the last transition)
* Declared  — ``declared_departure_*`` + ``declaration_source`` + evidence ref
* Estimated — ``estimated_minutes`` + ``estimate_basis`` (server-computed)
* Resolved  — ``outcome`` + ``decision_note`` (an administrative decision;
  "resolved" never means "duration verified")

``onsite_attendance_review_events`` is append-only: one row per transition,
written in the same transaction. There is no update or delete path.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow

EXCEPTION_TYPES = ("SINGLE_RECORDED_FINGERPRINT", "DEPARTURE_TIME_QUERY", "DISPUTED_SPAN", "DEVICE_ISSUE",
                   "IDENTITY_ISSUE", "OTHER")
STATUSES = ("OPEN", "SUBMITTED", "RESOLVED", "REOPENED")
REASONS = ("FORGOT_TO_RECORD", "DEVICE_FAULT", "ASSIGNED_OFF_SITE", "APPROVED_LEAVE_OR_DUTY", "OTHER")
SOURCES = ("TEAM_MEMBER_STATEMENT", "MANAGER_CONFIRMATION", "SECURITY_OR_VISITOR_LOG", "OTHER")
OUTCOMES = ("JUSTIFIED", "NO_FURTHER_ACTION", "NOT_JUSTIFIED")
IDENTITY_KINDS = ("PERSON", "CODE")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ",".join(f"'{v}'" for v in values) + ")"


class AttendanceReview(Base):
    __tablename__ = "onsite_attendance_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_id: Mapped[str] = mapped_column(String(64))
    local_date: Mapped[date] = mapped_column(Date)
    identity_kind: Mapped[str] = mapped_column(String(8))
    identity_key: Mapped[str] = mapped_column(String(96))
    bamboohr_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    zk_emp_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    identity_snapshot: Mapped[str] = mapped_column(Text)  # JSON, immutable after open

    exception_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    version: Mapped[int] = mapped_column(Integer, default=1)

    justification_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    declared_departure_local: Mapped[str | None] = mapped_column(String(40), nullable=True)
    declared_departure_utc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    declaration_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    evidence_reference: Mapped[str | None] = mapped_column(String(300), nullable=True)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimate_basis: Mapped[str | None] = mapped_column(Text, nullable=True)

    outcome: Mapped[str | None] = mapped_column(String(24), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    facts_snapshot: Mapped[str] = mapped_column(Text)  # JSON, replaced at open/submit/resolve

    opened_by_user_id: Mapped[int] = mapped_column(Integer)
    opened_by_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    submitted_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submitted_by_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolved_by_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reopened_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reopened_by_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reopen_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("site_id", "local_date", "identity_key", name="uq_review_identity_day"),
        CheckConstraint(_in("identity_kind", IDENTITY_KINDS), name="ck_review_kind"),
        CheckConstraint(_in("status", STATUSES), name="ck_review_status"),
        CheckConstraint(_in("exception_type", EXCEPTION_TYPES), name="ck_review_type"),
        CheckConstraint("version >= 1", name="ck_review_version"),
        Index("ix_review_site_date", "site_id", "local_date"),
        Index("ix_review_site_status", "site_id", "status"),
    )


class AttendanceReviewEvent(Base):
    __tablename__ = "onsite_attendance_review_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(Integer, ForeignKey("onsite_attendance_reviews.id"))
    action: Mapped[str] = mapped_column(String(16))  # OPEN | SUBMIT | UPDATE | RESOLVE | REOPEN
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str] = mapped_column(String(16))
    version: Mapped[int] = mapped_column(Integer)
    actor_user_id: Mapped[int] = mapped_column(Integer)
    actor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    previous_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    facts_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_review_event_review_at", "review_id", "at"),)
