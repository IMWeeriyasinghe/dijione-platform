"""audit_logs.event_id for the isolated DEV audit release

Same schema change as q7r8s9t0u1v2 (PR #89), descending from DEV's actual head.
Additive: one nullable column and a unique constraint. Existing rows and callers
that omit it are unaffected. The release line must not run both migrations; see
docs/platform/audit-migration-integration.md.

Revision ID: a7e1d0c4b9f2
Revises: o5p6q7r8s9t0
"""

import sqlalchemy as sa

from alembic import op

revision = "a7e1d0c4b9f2"
down_revision = "o5p6q7r8s9t0"
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
