"""Add DijiALERTS Coming Soon module to the application registry.

Revision ID: w5x7z9b1d3f5
Revises: v4w6y8a0c2e4

access_version: exempt — this migration inserts a single COMING_SOON module
row that grants no active user access and cannot be navigated to.  No user's
effective permission set changes, so no access_version bump is warranted.
"""

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "w5x7z9b1d3f5"
down_revision = "v4w6y8a0c2e4"
branch_labels = None
depends_on = None

_MODULE_KEY = "alerts"

_modules = sa.table(
    "application_modules",
    sa.column("key", sa.String),
    sa.column("name", sa.String),
    sa.column("description", sa.String),
    sa.column("icon", sa.String),
    sa.column("route", sa.String),
    sa.column("status", sa.String),
    sa.column("enabled", sa.Boolean),
    sa.column("display_order", sa.Integer),
    sa.column("required_roles", sa.String),
    sa.column("supports_client_scope", sa.Boolean),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    conn = op.get_bind()
    existing = sa.table("application_modules", sa.column("key", sa.String))
    row = conn.execute(sa.select(existing).where(existing.c.key == _MODULE_KEY)).first()
    if row is not None:
        return
    now = datetime.now(tz=UTC)
    op.bulk_insert(
        _modules,
        [
            {
                "key": _MODULE_KEY,
                "name": "DijiALERTS",
                "description": "Smart SMS Broadcasting & Emergency Communications",
                "icon": "BellAlert",
                "route": "/alerts",
                "status": "COMING_SOON",
                "enabled": True,
                "display_order": 6,
                "required_roles": "",
                "supports_client_scope": False,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


def downgrade() -> None:
    _t = sa.table("application_modules", sa.column("key", sa.String))
    op.execute(sa.delete(_t).where(_t.c.key == _MODULE_KEY))
