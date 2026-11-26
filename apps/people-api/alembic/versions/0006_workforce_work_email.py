"""Add work_email to workforce_directory for admin-only email search.

The column is nullable and indexed. It is populated during workforce sync
from BambooHR's workEmail field. It is never returned in WorkforceEntryOut
(minimum-data policy, CLAUDE.md rule 9) — only used server-side for the
admin search endpoint.

Revision ID: 0006_workforce_work_email
Revises: 0005_people_contact_numbers
Create Date: 2026-11-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_workforce_work_email"
down_revision = "0005_people_contact_numbers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workforce_directory") as batch_op:
        batch_op.add_column(
            sa.Column("work_email", sa.String(length=255), nullable=True)
        )
        batch_op.create_index("ix_workforce_directory_work_email", ["work_email"])


def downgrade() -> None:
    with op.batch_alter_table("workforce_directory") as batch_op:
        batch_op.drop_index("ix_workforce_directory_work_email")
        batch_op.drop_column("work_email")
