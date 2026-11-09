"""corrections, employee name snapshot and local settings

Revision ID: 0002_atwork_corrections
Revises: 0001_atwork_attendance
Create Date: 2026-11-09 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_atwork_corrections"
down_revision: str | Sequence[str] | None = "0001_atwork_attendance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TS = sa.DateTime(timezone=True)
_OPEN_OLD = sa.text("ended_at IS NULL")
_OPEN_NEW = sa.text("ended_at IS NULL AND voided_at IS NULL")
_PENDING = sa.text("status = 'PENDING' AND session_id IS NOT NULL")


def upgrade() -> None:
    with op.batch_alter_table("attendance_sessions") as batch:
        batch.add_column(sa.Column("origin", sa.String(16), nullable=False, server_default="RECORDED"))
        batch.add_column(sa.Column("correction_count", sa.Integer(), nullable=False, server_default="0"))

    op.drop_index("uq_attendance_breaks_one_open", table_name="attendance_breaks")
    with op.batch_alter_table("attendance_breaks") as batch:
        batch.add_column(sa.Column("voided_at", _TS, nullable=True))
        batch.add_column(sa.Column("voided_by_correction_id", sa.String(36), nullable=True))
    op.create_index(
        "uq_attendance_breaks_one_open", "attendance_breaks", ["session_id"], unique=True,
        sqlite_where=_OPEN_NEW, postgresql_where=_OPEN_NEW,
    )

    with op.batch_alter_table("attendance_events") as batch:
        batch.alter_column("session_id", existing_type=sa.String(36), nullable=True)

    op.create_table(
        "attendance_employees",
        sa.Column("platform_user_id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("last_seen_at", _TS, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    op.create_table(
        "correction_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("platform_user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("attendance_sessions.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("base_session_version", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("original", sa.JSON(), nullable=True),
        sa.Column("proposed", sa.JSON(), nullable=False),
        sa.Column("client_request_id", sa.String(64), nullable=False),
        sa.Column("reviewer_user_id", sa.Integer(), nullable=True),
        sa.Column("reviewer_name", sa.String(200), nullable=True),
        sa.Column("reviewed_at", _TS, nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", _TS, nullable=False),
        sa.Column("updated_at", _TS, nullable=False),
        sa.CheckConstraint("status IN ('PENDING', 'APPROVED', 'REJECTED', 'WITHDRAWN')", name="ck_correction_requests_status"),
        sa.CheckConstraint("kind IN ('AMEND', 'CREATE_MISSING')", name="ck_correction_requests_kind"),
        sa.UniqueConstraint("platform_user_id", "client_request_id", name="uq_correction_requests_client_request"),
    )
    op.create_index(
        "uq_correction_requests_one_pending", "correction_requests", ["session_id"], unique=True,
        sqlite_where=_PENDING, postgresql_where=_PENDING,
    )
    op.create_index("ix_correction_requests_user", "correction_requests", ["platform_user_id", "created_at"])
    op.create_index("ix_correction_requests_status", "correction_requests", ["status", "created_at"])
    op.create_table(
        "atwork_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("enabled_work_modes", sa.JSON(), nullable=False),
        sa.Column("business_time_zone", sa.String(64), nullable=False),
        sa.Column("missed_checkout_hours", sa.Integer(), nullable=False),
        sa.Column("time_format", sa.String(8), nullable=False),
        sa.Column("default_history_days", sa.Integer(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=False),
        sa.Column("updated_at", _TS, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_atwork_settings_single_row"),
    )


def downgrade() -> None:
    """Refuses to discard correction history or session-less audit events."""
    bind = op.get_bind()
    for label, sql in (
        ("correction requests", "SELECT count(*) FROM correction_requests"),
        ("non-session audit events", "SELECT count(*) FROM attendance_events WHERE session_id IS NULL"),
        ("voided breaks", "SELECT count(*) FROM attendance_breaks WHERE voided_at IS NOT NULL"),
    ):
        if bind.execute(sa.text(sql)).scalar():
            raise RuntimeError(f"Downgrade refused: {label} exist and would be lost.")
    op.drop_table("atwork_settings")
    op.drop_table("correction_requests")
    op.drop_table("attendance_employees")
    with op.batch_alter_table("attendance_events") as batch:
        batch.alter_column("session_id", existing_type=sa.String(36), nullable=False)
    op.drop_index("uq_attendance_breaks_one_open", table_name="attendance_breaks")
    with op.batch_alter_table("attendance_breaks") as batch:
        batch.drop_column("voided_by_correction_id")
        batch.drop_column("voided_at")
    op.create_index(
        "uq_attendance_breaks_one_open", "attendance_breaks", ["session_id"], unique=True,
        sqlite_where=_OPEN_OLD, postgresql_where=_OPEN_OLD,
    )
    with op.batch_alter_table("attendance_sessions") as batch:
        batch.drop_column("correction_count")
        batch.drop_column("origin")
