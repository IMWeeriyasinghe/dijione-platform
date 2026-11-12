"""activate DijiAtWork and its default employee access in UAT and PROD

Data migration only, modelled on m3n4o5p6q7r8 (Diji On-site). When APP_ENV is uat
or prod, the `atwork` registry row becomes ACTIVE and its ATWORK_USER baseline is
enabled. DEV is unchanged (already active through o5p6q7r8s9t0 and p6q7r8s9t0u1).
No role is assigned to anyone. Default access still needs a verified internal
employee: the Entra `acct` claim and ENTRA_INTERNAL_EMAIL_DOMAINS, else it grants
nothing.

Revision ID: e1f3a5b7c9d0
Revises: c9d2e4f6a8b1
Create Date: 2026-11-12 00:00:00.000000
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e1f3a5b7c9d0"
down_revision: str | Sequence[str] | None = "c9d2e4f6a8b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RELEASE_APP_ENVS = {"uat", "prod", "production"}


def _is_release_env() -> bool:
    return os.environ.get("APP_ENV", "development").strip().lower() in _RELEASE_APP_ENVS


def _apply(status: str, enabled: bool) -> None:
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE application_modules SET status = :s WHERE key = 'atwork'"), {"s": status})
    bind.execute(sa.text("UPDATE module_baseline_roles SET enabled = :e WHERE module_key = 'atwork'"), {"e": enabled})


def upgrade() -> None:
    if _is_release_env():
        _apply("ACTIVE", True)


def downgrade() -> None:
    if _is_release_env():
        _apply("COMING_SOON", False)
