"""activate the Diji On-site module registry row in UAT and PROD

Data migration only, forward-only in spirit: the approved Diji On-site V1
release makes the `onsite` application_modules row ACTIVE in UAT and PROD
(APP_ENV=uat / prod — the values main.bicep sets on those migrate jobs).
DEV was already activated by k1l2m3n4o5p6. Only the `onsite` row is
touched; DijiSpark and every other module keep their status.

Downgrade restores COMING_SOON for the same environments.

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-11-02 00:00:00.000000
"""

import os
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "m3n4o5p6q7r8"
down_revision: Union[str, Sequence[str], None] = "l2m3n4o5p6q7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RELEASE_APP_ENVS = {"uat", "prod", "production"}


def _is_release_env() -> bool:
    return os.environ.get("APP_ENV", "development").strip().lower() in _RELEASE_APP_ENVS


def _set_status(status: str) -> None:
    op.get_bind().execute(
        sa.text("UPDATE application_modules SET status = :s WHERE key = 'onsite'"), {"s": status}
    )


def upgrade() -> None:
    if _is_release_env():
        _set_status("ACTIVE")


def downgrade() -> None:
    if _is_release_env():
        _set_status("COMING_SOON")
