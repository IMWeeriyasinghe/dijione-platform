"""widen free-form Lever text columns to Text

Real Lever data (unlike the mock fixtures) carries posting locations,
team/department paths, candidate names and headlines, and archive reasons
that exceed varchar(255). The first live sync failed with
StringDataRightTruncation. These fields are pure source read-model text and
are never used as an authorization signal, so widen them to unbounded Text
(email goes to 320 — RFC 5321 max — while staying indexed).

Revision ID: 0002_widen_free_text
Revises: 0001_recruitment_initial
Create Date: 2026-09-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_widen_free_text"
down_revision: str | Sequence[str] | None = "0001_recruitment_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WIDEN = [
    ("postings", "title", sa.Text()),
    ("postings", "team", sa.Text()),
    ("postings", "department", sa.Text()),
    ("postings", "location", sa.Text()),
    ("recruitment_candidates", "full_name", sa.Text()),
    ("recruitment_candidates", "headline", sa.Text()),
    ("recruitment_candidates", "email", sa.String(length=320)),
    ("recruitment_candidacies", "lever_archive_reason", sa.Text()),
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # SQLite has no real VARCHAR length enforcement and ALTER COLUMN TYPE
        # is unsupported; the widening is a no-op there.
        return
    for table, column, type_ in _WIDEN:
        nullable = table == "recruitment_candidacies" and column == "lever_archive_reason"
        op.alter_column(table, column, type_=type_, existing_nullable=nullable)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    _revert = [
        ("postings", "title", sa.String(length=255)),
        ("postings", "team", sa.String(length=255)),
        ("postings", "department", sa.String(length=255)),
        ("postings", "location", sa.String(length=255)),
        ("recruitment_candidates", "full_name", sa.String(length=255)),
        ("recruitment_candidates", "headline", sa.String(length=255)),
        ("recruitment_candidates", "email", sa.String(length=255)),
        ("recruitment_candidacies", "lever_archive_reason", sa.String(length=255)),
    ]
    for table, column, type_ in _revert:
        nullable = table == "recruitment_candidacies" and column == "lever_archive_reason"
        op.alter_column(
            table, column, type_=type_,
            existing_nullable=nullable,
            postgresql_using=f"left({column}, {255 if type_.length == 255 else type_.length})",
        )
