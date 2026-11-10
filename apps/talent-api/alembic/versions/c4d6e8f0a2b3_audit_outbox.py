"""audit_outbox: reconcile audit events awaiting delivery to Platform Core

Additive: one new table.

Revision ID: c4d6e8f0a2b3
Revises: b3c5d7e9f1a2
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4d6e8f0a2b3"
down_revision: str | Sequence[str] | None = "b3c5d7e9f1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_token", sa.String(length=36), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=64), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", name="uq_audit_outbox_event_id"),
    )
    op.create_index("ix_audit_outbox_status_next_attempt", "audit_outbox", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_outbox_status_next_attempt", table_name="audit_outbox")
    op.drop_table("audit_outbox")
