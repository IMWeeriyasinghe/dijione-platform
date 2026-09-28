"""supplier_users invitation-send counters (Supplier Portal invitation workflow)

Additive/nullable-or-defaulted: invite_count, last_invited_by. invited_at
(added by f3a5b7c9d1e4) is reused as "last invite sent at" — unified
meaning, no new column for it: previously stamped only by an admin's
manual "IT already invited via out-of-band process" checkbox, now also
stamped automatically whenever the app actually sends the branded
invitation email.

Revision ID: ad84ec92abcb
Revises: ab10ac1cdce1
Create Date: 2026-09-30 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ad84ec92abcb"
down_revision: str | Sequence[str] | None = "ab10ac1cdce1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("supplier_users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("invite_count", sa.Integer(), nullable=False, server_default="0")
        )
        # No FK to users.id — User is owned by platform-api's own database
        # (same convention as OrderEvent.actor_id elsewhere in this app).
        batch_op.add_column(sa.Column("last_invited_by", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("supplier_users", schema=None) as batch_op:
        batch_op.drop_column("last_invited_by")
        batch_op.drop_column("invite_count")
