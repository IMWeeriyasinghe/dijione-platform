"""inbound supplier email — quarantine table + poll watermark (Phase 1 §1.5)

Additive. ``inbound_emails`` holds ONLY emails that could not be safely
correlated (the "Unmatched supplier email" queue); matched replies go
straight to ``supplier_communications``. ``inbound_poll_state`` is the
single-row mailbox-poll watermark.

Revision ID: e2f4a6b8c0d2
Revises: d1e3f5a7b9c2
Create Date: 2026-09-09 00:00:01.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e2f4a6b8c0d2"
down_revision: str | Sequence[str] | None = "d1e3f5a7b9c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inbound_emails",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=False),
        sa.Column("from_address", sa.String(length=320), nullable=False, server_default=""),
        sa.Column("subject", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("body_preview", sa.Text(), nullable=False, server_default=""),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attachment_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="UNMATCHED"),
        sa.Column("reason", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("linked_order_id", sa.Integer(), nullable=True),
        sa.Column("linked_by", sa.Integer(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        op.f("ix_inbound_emails_provider_message_id"),
        "inbound_emails", ["provider_message_id"], unique=True,
    )
    op.create_index(op.f("ix_inbound_emails_status"), "inbound_emails", ["status"], unique=False)

    op.create_table(
        "inbound_poll_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("inbound_poll_state")
    op.drop_index(op.f("ix_inbound_emails_status"), table_name="inbound_emails")
    op.drop_index(op.f("ix_inbound_emails_provider_message_id"), table_name="inbound_emails")
    op.drop_table("inbound_emails")
