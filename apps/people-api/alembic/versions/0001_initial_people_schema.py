"""initial People / Workforce schema

Architecture Completion Plan Wave E. The employee/workforce read model —
did not exist before this wave (birthday-api previously made a live
BambooHR call per request with nothing persisted). Tables: employees,
people_sync_runs.

Revision ID: 0001_people_initial
Revises:
Create Date: 2026-09-01 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0001_people_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bamboohr_id", sa.String(length=64), nullable=False),
        sa.Column("employee_number", sa.String(length=32), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("work_email", sa.String(length=255), nullable=False),
        sa.Column("birth_month", sa.Integer(), nullable=False),
        sa.Column("birth_day", sa.Integer(), nullable=False),
        sa.Column("department", sa.String(length=255), nullable=False),
        sa.Column("office_location", sa.String(length=255), nullable=False),
        sa.Column("employment_status", sa.String(length=32), nullable=False),
        sa.Column("hire_date", sa.Date(), nullable=True),
        sa.Column("termination_date", sa.Date(), nullable=True),
        sa.Column("address_line1", sa.String(length=255), nullable=True),
        sa.Column("address_line2", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=128), nullable=True),
        sa.Column("state_province", sa.String(length=128), nullable=True),
        sa.Column("postal_code", sa.String(length=32), nullable=True),
        sa.Column("country", sa.String(length=128), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("employees", schema=None) as b:
        b.create_index(b.f("ix_employees_bamboohr_id"), ["bamboohr_id"], unique=True)
        b.create_index(b.f("ix_employees_employee_number"), ["employee_number"], unique=False)

    op.create_table(
        "people_sync_runs",
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
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("people_sync_runs", schema=None) as b:
        b.create_index(b.f("ix_people_sync_runs_run_id"), ["run_id"], unique=True)
        b.create_index(b.f("ix_people_sync_runs_status"), ["status"], unique=False)


def downgrade() -> None:
    op.drop_table("people_sync_runs")
    op.drop_table("employees")
