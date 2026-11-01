"""activate the Diji On-site module registry row in DEV only

Data migration only. Diji On-site Dashboard V1 is released for DEV testing,
so in the DEV environment (APP_ENV=development — the value main.bicep sets on
every DEV migrate job) the `onsite` application_modules row moves from
COMING_SOON to ACTIVE, which gives its Home card an Open link. UAT/PROD
(APP_ENV=uat / prod) are deliberately untouched and keep COMING_SOON until a
separate approval. Only the `onsite` row is touched.

Downgrade restores COMING_SOON for the same environment.

Revision ID: k1l2m3n4o5p6
Revises: i9j0k1l2m3n4
Create Date: 2026-11-01 00:00:00.000000

Note: the unmerged local branch local/talent-module-admin adds revision
j0k1l2m3n4o5 on top of i9j0k1l2m3n4 as well; whichever merges second must
rebase its down_revision to keep a single head.
"""

import os
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "k1l2m3n4o5p6"
down_revision: Union[str, Sequence[str], None] = "i9j0k1l2m3n4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEV_APP_ENVS = {"development", "dev"}


def _is_dev() -> bool:
    return os.environ.get("APP_ENV", "development").strip().lower() in _DEV_APP_ENVS


def _set_status(status: str) -> None:
    op.get_bind().execute(
        sa.text("UPDATE application_modules SET status = :s WHERE key = 'onsite'"), {"s": status}
    )


def upgrade() -> None:
    if _is_dev():
        _set_status("ACTIVE")


def downgrade() -> None:
    if _is_dev():
        _set_status("COMING_SOON")
