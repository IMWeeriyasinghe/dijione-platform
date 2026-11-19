"""attendance review cases (v0.9) — additive

Adds two DijiOne-owned tables to onsite_<env>. No existing table, column or
row is touched: attendance_events stays a verbatim mirror and identity
mappings are unchanged, so ingestion and every v0.8 query are unaffected and
the v0.8 application image runs unchanged against this schema (rollback =
previous image, schema retained; review rows survive).

The downgrade exists for CI (fresh SQLite / Postgres upgrade-downgrade-upgrade)
only. It must never be run against DEV/UAT/PROD: recovery is forward-only.

Revision ID: 0003_onsite_attendance_reviews
Revises: 0002_onsite_identity
Create Date: 2026-11-19 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_onsite_attendance_reviews"
down_revision: Union[str, Sequence[str], None] = "0002_onsite_identity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KINDS = "identity_kind IN ('PERSON','CODE')"
_STATUSES = "status IN ('OPEN','SUBMITTED','RESOLVED','REOPENED')"
_TYPES = ("exception_type IN ('SINGLE_RECORDED_FINGERPRINT','DEPARTURE_TIME_QUERY','DISPUTED_SPAN',"
          "'DEVICE_ISSUE','IDENTITY_ISSUE','OTHER')")


def upgrade() -> None:
    op.create_table(
        "onsite_attendance_reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("site_id", sa.String(length=64), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("identity_kind", sa.String(length=8), nullable=False),
        sa.Column("identity_key", sa.String(length=96), nullable=False),
        sa.Column("bamboohr_id", sa.String(length=64), nullable=True),
        sa.Column("zk_emp_code", sa.String(length=20), nullable=True),
        sa.Column("identity_snapshot", sa.Text(), nullable=False),
        sa.Column("exception_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("justification_reason", sa.String(length=32), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("declared_departure_local", sa.String(length=40), nullable=True),
        sa.Column("declared_departure_utc", sa.DateTime(), nullable=True),
        sa.Column("declaration_source", sa.String(length=32), nullable=True),
        sa.Column("evidence_reference", sa.String(length=300), nullable=True),
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
        sa.Column("estimate_basis", sa.Text(), nullable=True),
        sa.Column("outcome", sa.String(length=24), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("facts_snapshot", sa.Text(), nullable=False),
        sa.Column("opened_by_user_id", sa.Integer(), nullable=False),
        sa.Column("opened_by_name", sa.String(length=200), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("submitted_by_name", sa.String(length=200), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("resolved_by_name", sa.String(length=200), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reopened_by_user_id", sa.Integer(), nullable=True),
        sa.Column("reopened_by_name", sa.String(length=200), nullable=True),
        sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reopen_reason", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_id", "local_date", "identity_key", name="uq_review_identity_day"),
        sa.CheckConstraint(_KINDS, name="ck_review_kind"),
        sa.CheckConstraint(_STATUSES, name="ck_review_status"),
        sa.CheckConstraint(_TYPES, name="ck_review_type"),
        sa.CheckConstraint("version >= 1", name="ck_review_version"),
    )
    op.create_index("ix_review_site_date", "onsite_attendance_reviews", ["site_id", "local_date"])
    op.create_index("ix_review_site_status", "onsite_attendance_reviews", ["site_id", "status"])

    op.create_table(
        "onsite_attendance_review_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("from_status", sa.String(length=16), nullable=True),
        sa.Column("to_status", sa.String(length=16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("actor_name", sa.String(length=200), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_json", sa.Text(), nullable=True),
        sa.Column("new_json", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("facts_snapshot", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["review_id"], ["onsite_attendance_reviews.id"],
                                name="fk_review_event_review"),
    )
    op.create_index("ix_review_event_review_at", "onsite_attendance_review_events", ["review_id", "at"])


def downgrade() -> None:  # CI only — never against a live environment
    op.drop_index("ix_review_event_review_at", table_name="onsite_attendance_review_events")
    op.drop_table("onsite_attendance_review_events")
    op.drop_index("ix_review_site_status", table_name="onsite_attendance_reviews")
    op.drop_index("ix_review_site_date", table_name="onsite_attendance_reviews")
    op.drop_table("onsite_attendance_reviews")
