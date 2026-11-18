"""operational start date, global supplier lead time, clean-start marker;
single supplier role

Revision ID: b5e7c9d1f3a2
Revises: ad84ec92abcb
Create Date: 2026-11-18

Additive and backward-safe: images built before this revision ignore the
new columns. The supplier_users.role normalisation is data-only (the
column stays) and is not reversed on downgrade — every value it writes
was already valid.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b5e7c9d1f3a2"
down_revision: str | Sequence[str] | None = "ad84ec92abcb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("birthday_detection_configs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("operational_start_date", sa.Date(), nullable=True))
        batch_op.add_column(
            sa.Column("supplier_lead_time_days", sa.Integer(), nullable=False, server_default="7")
        )
        batch_op.add_column(sa.Column("clean_start_applied_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("clean_start_applied_by", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("clean_start_excluded_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("clean_start_first_eligible", sa.Date(), nullable=True))

    op.execute("UPDATE supplier_users SET role = 'SUPPLIER_USER' WHERE role <> 'SUPPLIER_USER'")


def downgrade() -> None:
    with op.batch_alter_table("birthday_detection_configs", schema=None) as batch_op:
        batch_op.drop_column("clean_start_first_eligible")
        batch_op.drop_column("clean_start_excluded_count")
        batch_op.drop_column("clean_start_applied_by")
        batch_op.drop_column("clean_start_applied_at")
        batch_op.drop_column("supplier_lead_time_days")
        batch_op.drop_column("operational_start_date")
