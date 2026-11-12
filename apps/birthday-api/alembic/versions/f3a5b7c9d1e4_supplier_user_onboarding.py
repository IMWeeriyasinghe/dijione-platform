"""supplier_users onboarding-state timestamps (Phase 1 §1.6)

Additive/nullable: invited_at, linked_at, last_login_at.

Revision ID: f3a5b7c9d1e4
Revises: e2f4a6b8c0d2
Create Date: 2026-09-09 00:00:02.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f3a5b7c9d1e4"
down_revision: str | Sequence[str] | None = "e2f4a6b8c0d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("supplier_users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("supplier_users", schema=None) as batch_op:
        batch_op.drop_column("last_login_at")
        batch_op.drop_column("linked_at")
        batch_op.drop_column("invited_at")
