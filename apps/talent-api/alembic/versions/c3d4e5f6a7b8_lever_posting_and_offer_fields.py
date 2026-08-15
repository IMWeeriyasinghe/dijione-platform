"""Lever posting read model, client-mapping authorization table, and
Application offer/archive-reason diagnostic fields.

Additive only. ``postings`` mirrors Lever-sourced vacancy data;
``posting_client_mappings`` is a separate table for the DijiOne-owned,
fail-closed-by-default Posting -> Client authorization relationship (never
columns on ``postings``, so a future Lever re-sync can never clobber
verification state). See CLAUDE.md §60 live Lever tenant discovery and the
Lever Integration Foundation implementation.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-15 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "postings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lever_posting_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("team", sa.String(length=255), nullable=False),
        sa.Column("department", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=False),
        sa.Column("owner_user_id", sa.String(length=128), nullable=False),
        sa.Column("hiring_manager_user_id", sa.String(length=128), nullable=False),
        sa.Column("confidentiality", sa.String(length=32), nullable=False),
        sa.Column("tags", sa.Text(), nullable=False),
        sa.Column("lever_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lever_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lever_posting_id"),
    )
    with op.batch_alter_table("postings", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_postings_lever_posting_id"), ["lever_posting_id"], unique=True
        )

    op.create_table(
        "posting_client_mappings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("posting_id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("verified_by_user_id", sa.Integer(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["posting_id"], ["postings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("posting_id"),
    )
    with op.batch_alter_table("posting_client_mappings", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_posting_client_mappings_posting_id"), ["posting_id"], unique=True
        )
        batch_op.create_index(
            batch_op.f("ix_posting_client_mappings_client_id"), ["client_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_posting_client_mappings_status"), ["status"], unique=False
        )

    with op.batch_alter_table("applications", schema=None) as batch_op:
        batch_op.add_column(sa.Column("lever_archive_reason", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("lever_offer_status", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column("lever_offer_created_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("applications", schema=None) as batch_op:
        batch_op.drop_column("lever_offer_created_at")
        batch_op.drop_column("lever_offer_status")
        batch_op.drop_column("lever_archive_reason")

    with op.batch_alter_table("posting_client_mappings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_posting_client_mappings_status"))
        batch_op.drop_index(batch_op.f("ix_posting_client_mappings_client_id"))
        batch_op.drop_index(batch_op.f("ix_posting_client_mappings_posting_id"))
    op.drop_table("posting_client_mappings")

    with op.batch_alter_table("postings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_postings_lever_posting_id"))
    op.drop_table("postings")
