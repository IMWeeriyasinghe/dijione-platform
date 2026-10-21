"""generic Workforce Directory read model

Additive only: creates workforce_directory and workforce_sync_runs. The
Birthday-oriented Employee contract (employees, people_sync_runs) is not
touched. See docs/platform/workforce-directory.md.

Revision ID: 0003_people_workforce
Revises: 0002_people_drop_mock
Create Date: 2026-10-22 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_people_workforce"
down_revision: str | Sequence[str] | None = "0002_people_drop_mock"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workforce_directory",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bamboohr_id", sa.String(length=64), nullable=False),
        sa.Column("employee_number", sa.String(length=32), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("department", sa.String(length=255), nullable=False),
        sa.Column("job_title", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=False),
        sa.Column("employment_status", sa.String(length=32), nullable=False),
        sa.Column("hire_date", sa.Date(), nullable=True),
        sa.Column("termination_date", sa.Date(), nullable=True),
        sa.Column("present_in_source", sa.Boolean(), nullable=False),
        sa.Column("first_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workforce_directory_bamboohr_id"), "workforce_directory", ["bamboohr_id"], unique=True)
    op.create_index(op.f("ix_workforce_directory_employee_number"), "workforce_directory", ["employee_number"], unique=False)
    op.create_index(op.f("ix_workforce_directory_employment_status"), "workforce_directory", ["employment_status"], unique=False)

    op.create_table(
        "workforce_sync_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("trigger_type", sa.String(length=16), nullable=False),
        sa.Column("requested_by_application", sa.String(length=64), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("records_read", sa.Integer(), nullable=False),
        sa.Column("records_created", sa.Integer(), nullable=False),
        sa.Column("records_updated", sa.Integer(), nullable=False),
        sa.Column("records_unchanged", sa.Integer(), nullable=False),
        sa.Column("records_absent", sa.Integer(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workforce_sync_runs_run_id"), "workforce_sync_runs", ["run_id"], unique=True)
    op.create_index(op.f("ix_workforce_sync_runs_status"), "workforce_sync_runs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_workforce_sync_runs_status"), table_name="workforce_sync_runs")
    op.drop_index(op.f("ix_workforce_sync_runs_run_id"), table_name="workforce_sync_runs")
    op.drop_table("workforce_sync_runs")
    op.drop_index(op.f("ix_workforce_directory_employment_status"), table_name="workforce_directory")
    op.drop_index(op.f("ix_workforce_directory_employee_number"), table_name="workforce_directory")
    op.drop_index(op.f("ix_workforce_directory_bamboohr_id"), table_name="workforce_directory")
    op.drop_table("workforce_directory")
