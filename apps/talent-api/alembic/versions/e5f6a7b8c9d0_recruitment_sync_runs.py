"""recruitment_sync_runs — durable Recruitment Source (Lever) sync-run state
for the DijiOne standard source-sync lifecycle. Additive only; no secrets or
raw PII stored (counts + safe error summary only).

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-31 10:45:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recruitment_sync_runs",
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
        sa.UniqueConstraint("run_id"),
    )
    with op.batch_alter_table("recruitment_sync_runs", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_recruitment_sync_runs_run_id"), ["run_id"], unique=True
        )
        batch_op.create_index(
            batch_op.f("ix_recruitment_sync_runs_status"), ["status"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("recruitment_sync_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_recruitment_sync_runs_status"))
        batch_op.drop_index(batch_op.f("ix_recruitment_sync_runs_run_id"))
    op.drop_table("recruitment_sync_runs")
