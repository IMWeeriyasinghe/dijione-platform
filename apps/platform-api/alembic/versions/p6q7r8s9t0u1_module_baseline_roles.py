"""internal-employee marker and per-module baseline roles

Additive. Adds users.internal_employee (false until the next verified Entra sign-in)
and module_baseline_roles. DijiAtWork's ATWORK_USER baseline is enabled in DEV only
(APP_ENV=development); elsewhere the row exists but is disabled. No user is granted
a stored role.

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
Create Date: 2026-11-10 12:00:00.000000
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "p6q7r8s9t0u1"
down_revision: str | Sequence[str] | None = "o5p6q7r8s9t0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Safe to re-run, like the other registration migrations.
    inspector = sa.inspect(op.get_bind())
    if "internal_employee" not in {c["name"] for c in inspector.get_columns("users")}:
        with op.batch_alter_table("users") as batch:
            batch.add_column(sa.Column("internal_employee", sa.Boolean(), nullable=False, server_default=sa.false()))
    if inspector.has_table("module_baseline_roles"):
        return
    table = op.create_table(
        "module_baseline_roles",
        sa.Column("module_key", sa.String(64), primary_key=True),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    is_dev = os.environ.get("APP_ENV", "development").strip().lower() in {"development", "dev"}
    op.bulk_insert(table, [{"module_key": "atwork", "role": "ATWORK_USER", "enabled": is_dev}])


def downgrade() -> None:
    op.drop_table("module_baseline_roles")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("internal_employee")
