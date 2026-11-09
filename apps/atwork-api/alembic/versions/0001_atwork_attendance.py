"""initial DijiAtWork attendance schema

Revision ID: 0001_atwork_attendance
Revises:
Create Date: 2026-11-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_atwork_attendance"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TS = sa.DateTime(timezone=True)


def _partial(name: str, table: str, columns: list[str], where: str) -> None:
    clause = sa.text(where)
    op.create_index(name, table, columns, unique=True, sqlite_where=clause, postgresql_where=clause)


def upgrade() -> None:
    op.create_table(
        "attendance_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("platform_user_id", sa.Integer(), nullable=False),
        sa.Column("work_mode", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("check_in_at", _TS, nullable=False),
        sa.Column("check_out_at", _TS, nullable=True),
        sa.Column("time_zone", sa.String(64), nullable=False),
        sa.Column("check_in_request_id", sa.String(64), nullable=False),
        sa.Column("check_out_request_id", sa.String(64), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", _TS, nullable=False),
        sa.Column("updated_at", _TS, nullable=False),
        sa.CheckConstraint("work_mode IN ('OFFICE', 'REMOTE', 'CLIENT_SITE')", name="ck_attendance_sessions_work_mode"),
        sa.CheckConstraint("status IN ('OPEN', 'COMPLETED')", name="ck_attendance_sessions_status"),
        sa.CheckConstraint("check_out_at IS NULL OR check_out_at >= check_in_at", name="ck_attendance_sessions_order"),
        sa.CheckConstraint("status <> 'OPEN' OR check_out_at IS NULL", name="ck_attendance_sessions_open_no_checkout"),
        sa.CheckConstraint("status <> 'COMPLETED' OR check_out_at IS NOT NULL", name="ck_attendance_sessions_completed_checkout"),
        sa.UniqueConstraint("platform_user_id", "check_in_request_id", name="uq_attendance_sessions_check_in_request"),
    )
    _partial("uq_attendance_sessions_one_open", "attendance_sessions", ["platform_user_id"], "status = 'OPEN'")
    _partial(
        "uq_attendance_sessions_check_out_request",
        "attendance_sessions",
        ["platform_user_id", "check_out_request_id"],
        "check_out_request_id IS NOT NULL",
    )
    op.create_index("ix_attendance_sessions_user_check_in", "attendance_sessions", ["platform_user_id", "check_in_at"])

    op.create_table(
        "attendance_breaks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("attendance_sessions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("started_at", _TS, nullable=False),
        sa.Column("ended_at", _TS, nullable=True),
        sa.Column("start_request_id", sa.String(64), nullable=False),
        sa.Column("end_request_id", sa.String(64), nullable=True),
        sa.Column("created_at", _TS, nullable=False),
        sa.Column("updated_at", _TS, nullable=False),
        sa.CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="ck_attendance_breaks_order"),
        sa.UniqueConstraint("session_id", "start_request_id", name="uq_attendance_breaks_start_request"),
    )
    _partial("uq_attendance_breaks_one_open", "attendance_breaks", ["session_id"], "ended_at IS NULL")
    _partial(
        "uq_attendance_breaks_end_request", "attendance_breaks", ["session_id", "end_request_id"], "end_request_id IS NOT NULL"
    )

    op.create_table(
        "attendance_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("subject_user_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("attendance_sessions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("occurred_at", _TS, nullable=False),
        sa.Column("before_state", sa.JSON(), nullable=True),
        sa.Column("after_state", sa.JSON(), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("correlation_id", sa.String(128), nullable=True),
    )
    op.create_index("ix_attendance_events_session", "attendance_events", ["session_id", "occurred_at"])
    op.create_index("ix_attendance_events_subject", "attendance_events", ["subject_user_id", "occurred_at"])


def downgrade() -> None:
    op.drop_table("attendance_events")
    op.drop_table("attendance_breaks")
    op.drop_table("attendance_sessions")
