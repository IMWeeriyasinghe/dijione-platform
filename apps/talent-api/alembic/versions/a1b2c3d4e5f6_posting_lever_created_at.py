"""recruitment_posting_refs.lever_created_at — postings "Created" column

DijiTalentFlow Monitoring-First UX & Client Access Refinement, PR 2.
Purely additive: one new nullable column on the existing
``recruitment_posting_refs`` projection table, populated on the next
reconcile from recruitment-api's already-exposed ``PostingOut
.lever_created_at`` fact (no cross-service schema change — the field was
already on the wire, just not persisted). Backs the staff Recruitment
Postings screen's new "Created" column.

Revision ID: a1b2c3d4e5f6
Revises: e7f8a9b0c1d2
Create Date: 2026-09-03 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "recruitment_posting_refs",
        sa.Column("lever_created_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("recruitment_posting_refs", "lever_created_at")
