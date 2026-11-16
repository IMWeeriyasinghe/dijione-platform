"""users.access_version: the per-user counter session tokens are checked against

Additive and reversible. One column, no index, no data change:

    ALTER TABLE users ADD COLUMN access_version INTEGER NOT NULL DEFAULT 0

On PostgreSQL 11+ a constant default is stored in the catalog, so the table is not
rewritten; the lock is brief. Existing sessions carry no ``av`` claim and are read as
version 0, so nothing is revoked by this migration.

Revision ID: h4j6k8m0n2p3
Revises: g3h5j7k9m1n2
Create Date: 2026-11-16 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "h4j6k8m0n2p3"
down_revision: str | Sequence[str] | None = "g3h5j7k9m1n2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("users")}
    if "access_version" in columns:
        return  # safe to re-run
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("access_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("users")}
    if "access_version" not in columns:
        return
    with op.batch_alter_table("users") as batch:
        batch.drop_column("access_version")
