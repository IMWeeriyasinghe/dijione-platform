"""notification link and per-recipient deduplication

Revision ID: n4o5p6q7r8s9
Revises: atw3perm1d4e5
Create Date: 2026-11-09 18:00:00.000000

Additive and generic: existing rows keep NULLs, which never collide.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "n4o5p6q7r8s9"
down_revision: str | Sequence[str] | None = "atw3perm1d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Safe to re-run, like the other registration migrations.
    if "link_url" in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("notifications")}:
        return
    with op.batch_alter_table("notifications") as batch:
        batch.add_column(sa.Column("link_url", sa.String(500), nullable=True))
        batch.add_column(sa.Column("dedupe_key", sa.String(200), nullable=True))
    with op.batch_alter_table("notifications") as batch:
        batch.create_unique_constraint("uq_notifications_user_dedupe", ["user_id", "dedupe_key"])


def downgrade() -> None:
    with op.batch_alter_table("notifications") as batch:
        batch.drop_constraint("uq_notifications_user_dedupe", type_="unique")
    with op.batch_alter_table("notifications") as batch:
        batch.drop_column("dedupe_key")
        batch.drop_column("link_url")
