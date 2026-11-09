"""activate the DijiAtWork module registry row in DEV only

Data migration only. In DEV (APP_ENV=development, set on every DEV migrate job)
the `atwork` row moves from COMING_SOON to ACTIVE, giving its Home card an Open
link for users who hold a DijiAtWork role. UAT and PROD keep COMING_SOON. No
role or permission is granted, and only the `atwork` row is touched.

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-11-10 00:00:00.000000
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "o5p6q7r8s9t0"
down_revision: str | Sequence[str] | None = "n4o5p6q7r8s9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_dev() -> bool:
    return os.environ.get("APP_ENV", "development").strip().lower() in {"development", "dev"}


def _set_status(status: str) -> None:
    op.get_bind().execute(sa.text("UPDATE application_modules SET status = :s WHERE key = 'atwork'"), {"s": status})


def upgrade() -> None:
    if _is_dev():
        _set_status("ACTIVE")


def downgrade() -> None:
    if _is_dev():
        _set_status("COMING_SOON")
