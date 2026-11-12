"""communication subsystem — extend supplier_communications for the unified
per-order timeline (Phase 1 §1.4).

Purely additive/nullable columns + indexes. ``supplier_communications``
becomes the single store for every message on every channel/direction:
adds author_type/author_id, in_reply_to, next_retry_at/max_attempts,
issue_id (FK order_issues), and an index on message_id for inbound dedupe.

Revision ID: d1e3f5a7b9c2
Revises: c4f6a8b0d2e4_drop_mock_orders
Create Date: 2026-09-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d1e3f5a7b9c2"
down_revision: str | Sequence[str] | None = "c4f6a8b0d2e4_drop_mock_orders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("supplier_communications", schema=None) as batch_op:
        batch_op.add_column(sa.Column("author_type", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("author_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("in_reply_to", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5")
        )
        batch_op.add_column(sa.Column("issue_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_supplier_communications_message_id"), ["message_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_supplier_communications_issue_id"), ["issue_id"], unique=False
        )
        batch_op.create_foreign_key(
            "fk_supplier_communications_issue_id",
            "order_issues", ["issue_id"], ["id"], ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("supplier_communications", schema=None) as batch_op:
        batch_op.drop_constraint("fk_supplier_communications_issue_id", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_supplier_communications_issue_id"))
        batch_op.drop_index(batch_op.f("ix_supplier_communications_message_id"))
        batch_op.drop_column("issue_id")
        batch_op.drop_column("max_attempts")
        batch_op.drop_column("next_retry_at")
        batch_op.drop_column("in_reply_to")
        batch_op.drop_column("author_id")
        batch_op.drop_column("author_type")
