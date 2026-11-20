"""Dedicated notification-administration permissions

Additive. Registers ``platform.admin.view_notifications`` and
``platform.admin.manage_notifications`` and links both to the SUPER_ADMIN and PLATFORM_ADMIN
platform roles. No other role is touched and no existing link is removed. It raises every
user's ``access_version`` so sessions issued before the permissions existed are re-issued with
them. Re-running is safe.

Revision ID: u3v5x7z9b1d3
Revises: t2u4w6y8a0c2
Create Date: 2026-11-21 00:00:00.000000
"""

import time
from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa

from alembic import op

revision: str = "u3v5x7z9b1d3"
down_revision: str | Sequence[str] | None = "t2u4w6y8a0c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION_KEYS = ("platform.admin.view_notifications", "platform.admin.manage_notifications")
ROLE_KEYS = ("SUPER_ADMIN", "PLATFORM_ADMIN")


def upgrade() -> None:
    from app.core.permissions import PLATFORM_PERMISSIONS

    bind = op.get_bind()
    now = datetime.now(timezone.utc)
    lookup = sa.text("SELECT id FROM permissions WHERE key = :k")
    permissions_table = sa.table(
        "permissions",
        sa.column("key", sa.String), sa.column("name", sa.String), sa.column("description", sa.Text),
        sa.column("module_key", sa.String), sa.column("category", sa.String),
        sa.column("created_at", sa.DateTime), sa.column("updated_at", sa.DateTime),
    )
    links = sa.table("role_permissions", sa.column("role_id", sa.Integer), sa.column("permission_id", sa.Integer))
    for key in PERMISSION_KEYS:
        perm = next(p for p in PLATFORM_PERMISSIONS if p.key == key)
        row = bind.execute(lookup, {"k": key}).first()
        if row is None:
            op.bulk_insert(permissions_table, [{
                "key": perm.key, "name": perm.name, "description": perm.description, "module_key": None,
                "category": perm.category, "created_at": now, "updated_at": now,
            }])
            row = bind.execute(lookup, {"k": key}).first()
        for role_key in ROLE_KEYS:
            role = bind.execute(
                sa.text("SELECT id FROM roles WHERE key = :k AND module_key IS NULL"), {"k": role_key}
            ).first()
            if role is None:
                continue
            linked = bind.execute(
                sa.text("SELECT 1 FROM role_permissions WHERE role_id = :r AND permission_id = :p"),
                {"r": role[0], "p": row[0]},
            ).first()
            if linked is None:
                op.bulk_insert(links, [{"role_id": role[0], "permission_id": row[0]}])
    # New permissions change what an administrator's session should carry (same rule as
    # app/services/access_version.py: max(old + 1, now)).
    bind.execute(
        sa.text(
            "UPDATE users SET access_version = CASE WHEN access_version + 1 > :floor "
            "THEN access_version + 1 ELSE :floor END"
        ),
        {"floor": int(time.time())},
    )


def downgrade() -> None:
    # Kept, like the other permission-registration migrations: removing them could orphan grants.
    pass
