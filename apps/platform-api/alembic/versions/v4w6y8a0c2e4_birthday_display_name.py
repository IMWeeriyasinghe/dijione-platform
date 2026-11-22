"""DIJI Birthday: the application registry display name used everywhere (and in email subjects).

Idempotent data change: only the ``birthday`` row's name, key unchanged. A registry change is
platform-wide, so access snapshots are realigned silently at startup; no email is queued.

Revision ID: v4w6y8a0c2e4
Revises: u3v5x7z9b1d3
"""

import time

import sqlalchemy as sa
from alembic import op

revision = "v4w6y8a0c2e4"
down_revision = "u3v5x7z9b1d3"
branch_labels = None
depends_on = None

_modules = sa.table("application_modules", sa.column("key", sa.String), sa.column("name", sa.String))


def _rename(name: str) -> None:
    bind = op.get_bind()
    bind.execute(_modules.update().where(_modules.c.key == "birthday").values(name=name))
    # Module names travel in session claims; re-issue sessions (same rule as
    # app/services/access_version.py: max(old + 1, now)). Not an access change: no email.
    bind.execute(
        sa.text(
            "UPDATE users SET access_version = CASE WHEN access_version + 1 > :floor "
            "THEN access_version + 1 ELSE :floor END"
        ),
        {"floor": int(time.time())},
    )


def upgrade() -> None:
    _rename("DIJI Birthday")


def downgrade() -> None:
    _rename("DijiBirthday")
