"""audit_logs.event_id: caller-supplied key that makes a retried event idempotent

Additive: one nullable column and a unique index. Existing rows and callers
that omit it are unaffected.

Revision ID: q7r8s9t0u1v2
Revises: p6q7r8s9t0u1
"""

import sqlalchemy as sa

from alembic import op

revision = "q7r8s9t0u1v2"
down_revision = "p6q7r8s9t0u1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.add_column(sa.Column("event_id", sa.String(length=64), nullable=True))
        batch_op.create_unique_constraint("uq_audit_logs_event_id", ["event_id"])


def downgrade() -> None:
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.drop_constraint("uq_audit_logs_event_id", type_="unique")
        batch_op.drop_column("event_id")
