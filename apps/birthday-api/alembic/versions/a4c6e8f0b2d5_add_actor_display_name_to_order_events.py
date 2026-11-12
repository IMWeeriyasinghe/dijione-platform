"""order_events.actor_display_name (Phase 1.6 §17)

Additive/nullable — no backfill. NULL for any event written before this
migration; the internal event-log UI falls back to actor_type for those.

Revision ID: a4c6e8f0b2d5
Revises: f3a5b7c9d1e4
Create Date: 2026-09-14 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a4c6e8f0b2d5"
down_revision: str | Sequence[str] | None = "f3a5b7c9d1e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("order_events", schema=None) as batch_op:
        batch_op.add_column(sa.Column("actor_display_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("order_events", schema=None) as batch_op:
        batch_op.drop_column("actor_display_name")
