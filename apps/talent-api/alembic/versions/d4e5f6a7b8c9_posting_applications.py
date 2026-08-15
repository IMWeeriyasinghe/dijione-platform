"""PostingApplication — Candidate x Posting candidacy synced from Lever
Opportunities, deliberately separate from the client-owned Application/
TalentRequest tables (see app/models/posting_application.py docstring).
Additive only.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-15 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "posting_applications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("posting_id", sa.Integer(), nullable=False),
        sa.Column("lever_opportunity_id", sa.String(length=128), nullable=False),
        sa.Column("current_stage", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("lever_archive_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["posting_id"], ["postings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # No (candidate_id, posting_id) uniqueness: a candidate can have
        # multiple distinct Opportunities against the same Posting (real
        # Lever data confirmed this — e.g. reapplication over time). Only
        # the Lever Opportunity id is a safe uniqueness boundary.
        sa.UniqueConstraint("lever_opportunity_id"),
    )
    with op.batch_alter_table("posting_applications", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_posting_applications_candidate_id"), ["candidate_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_posting_applications_posting_id"), ["posting_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_posting_applications_lever_opportunity_id"),
            ["lever_opportunity_id"], unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("posting_applications", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_posting_applications_lever_opportunity_id"))
        batch_op.drop_index(batch_op.f("ix_posting_applications_posting_id"))
        batch_op.drop_index(batch_op.f("ix_posting_applications_candidate_id"))
    op.drop_table("posting_applications")
