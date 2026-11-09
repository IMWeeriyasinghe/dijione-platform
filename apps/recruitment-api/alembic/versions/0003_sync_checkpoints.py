"""per-posting read checkpoints and sync run detail

Additive and nullable, so existing rows and the previous image keep working.

Revision ID: 0003_sync_checkpoints
Revises: 0002_widen_free_text
Create Date: 2026-11-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_sync_checkpoints"
down_revision: str | Sequence[str] | None = "0002_widen_free_text"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("postings", sa.Column("dtc_last_read_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("postings", sa.Column("dtc_last_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("recruitment_sync_runs", sa.Column("detail", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("recruitment_sync_runs", "detail")
    op.drop_column("postings", "dtc_last_attempt_at")
    op.drop_column("postings", "dtc_last_read_at")
