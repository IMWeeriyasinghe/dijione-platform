"""widen Lever-projected free-text columns to Text

The first live recruitment reconcile against real Lever data failed with
StringDataRightTruncation on candidates.professional_title (real candidate
headlines run 300+ chars; the mock fixtures never did), rolling back the
whole reconcile so no PostingClientMapping was ever committed. Widen the
Lever-projected free-text columns to unbounded Text (candidate email ->
String(320), RFC 5321 max, still indexed).

Revision ID: b3c5d7e9f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-09-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b3c5d7e9f1a2"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WIDEN = [
    ("candidates", "full_name", sa.Text(), False),
    ("candidates", "professional_title", sa.Text(), False),
    ("candidates", "email", sa.String(length=320), True),
    ("recruitment_posting_refs", "title", sa.Text(), False),
    ("recruitment_posting_refs", "location", sa.Text(), False),
    ("applications", "lever_archive_reason", sa.Text(), True),
]


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return
    for table, column, type_, nullable in _WIDEN:
        op.alter_column(table, column, type_=type_, existing_nullable=nullable)


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return
    for table, column, _type, nullable in _WIDEN:
        op.alter_column(
            table, column, type_=sa.String(length=255),
            existing_nullable=nullable,
            postgresql_using=f"left({column}, 255)",
        )
