"""Verified ZKBioTime ID -> BambooHR identity mappings (DijiOne-owned).

A ZKBioTime biometric code (``zk_emp_code`` = the mirror's ``emp_code``,
verbatim) is linked to a BambooHR employee (``bamboohr_id``, the stable
Workforce Directory key) only by an administrator, for an explicit inclusive
site-local date period. Raw attendance events are never modified; identity
is resolved at read time per ``(site_id, emp_code, site_local_date)``.

- ``onsite_identity_mappings``: one row = one verified ownership period.
  Rows are never deleted; ``SUPERSEDED`` is terminal.
- ``onsite_identity_rejections``: "this code is NOT this person" (optionally
  for a bounded period). Never attributes anything.
- ``onsite_identity_events``: durable local history of every write (the
  platform audit call is best-effort; this table is not).

BambooHR Employee Number is stored only as an audit snapshot — it is never a
key and never used for attribution.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, utcnow

MAPPING_VERIFIED = "VERIFIED"
MAPPING_SUPERSEDED = "SUPERSEDED"
REJECTION_ACTIVE = "ACTIVE"
REJECTION_WITHDRAWN = "WITHDRAWN"
SOURCE_MANUAL = "MANUAL"
SOURCE_IMPORT = "IMPORT"


class IdentityMapping(TimestampMixin, Base):
    __tablename__ = "onsite_identity_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_id: Mapped[str] = mapped_column(String(64))
    zk_emp_code: Mapped[str] = mapped_column(String(20))
    bamboohr_id: Mapped[str] = mapped_column(String(64))
    employee_number_snapshot: Mapped[str | None] = mapped_column(String(32), nullable=True)
    display_name_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=MAPPING_VERIFIED)
    evidence: Mapped[str] = mapped_column(Text)
    verified_by_user_id: Mapped[int] = mapped_column(Integer)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    superseded_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    superseded_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default=SOURCE_MANUAL)
    import_batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    __table_args__ = (
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="ck_idmap_period"),
        CheckConstraint("status IN ('VERIFIED','SUPERSEDED')", name="ck_idmap_status"),
        CheckConstraint("source IN ('MANUAL','IMPORT')", name="ck_idmap_source"),
        Index("ix_idmap_site_code_from", "site_id", "zk_emp_code", "valid_from"),
        Index("ix_idmap_bamboohr", "bamboohr_id"),
        # Second line of defence behind the service's overlap check: at most
        # one open-ended verified period per code and site.
        Index("ux_idmap_open_verified", "site_id", "zk_emp_code", unique=True,
              sqlite_where=text("status = 'VERIFIED' AND valid_to IS NULL"),
              postgresql_where=text("status = 'VERIFIED' AND valid_to IS NULL")),
    )

    def covers(self, day: date) -> bool:
        return self.valid_from <= day and (self.valid_to is None or day <= self.valid_to)


class IdentityRejection(TimestampMixin, Base):
    __tablename__ = "onsite_identity_rejections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_id: Mapped[str] = mapped_column(String(64))
    zk_emp_code: Mapped[str] = mapped_column(String(20))
    bamboohr_id: Mapped[str] = mapped_column(String(64))
    applies_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    applies_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default=REJECTION_ACTIVE)
    rejected_by_user_id: Mapped[int] = mapped_column(Integer)
    rejected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    withdrawn_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawn_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("applies_to IS NULL OR applies_from IS NULL OR applies_to >= applies_from",
                        name="ck_idrej_period"),
        CheckConstraint("status IN ('ACTIVE','WITHDRAWN')", name="ck_idrej_status"),
        Index("ix_idrej_pair", "site_id", "zk_emp_code", "bamboohr_id"),
    )

    def overlaps(self, start: date, end: date | None) -> bool:
        lo = self.applies_from or date.min
        hi = self.applies_to or date.max
        return lo <= (end or date.max) and start <= hi


class IdentityEvent(Base):
    __tablename__ = "onsite_identity_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(16))  # MAPPING | REJECTION | IMPORT
    entity_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(32))
    actor_user_id: Mapped[int] = mapped_column(Integer)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    previous_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_idev_entity", "entity_type", "entity_id"),
        Index("ix_idev_at", "at"),
    )
