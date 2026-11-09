"""add DijiAtWork V1 granular permissions

Data migration only. Get-or-create of the corrections, Management, reports,
settings and audit permissions and their links to the existing DijiAtWork roles, so existing
assignments receive them at the next token issue. Only DijiAtWork rows are
touched, and the module's status is never changed.

Revision ID: atw3perm1d4e5
Revises: atw2att0c3d4
Create Date: 2026-11-09 00:00:00.000000
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "atw3perm1d4e5"
down_revision: str | Sequence[str] | None = "atw2att0c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_KEYS = {
    "atwork.corrections.request_own", "atwork.attendance.read", "atwork.corrections.review", "atwork.corrections.approve",
    "atwork.reports.read", "atwork.reports.export", "atwork.settings.manage", "atwork.audit.read",
}


def upgrade() -> None:
    from app.core.constants import MODULE_ATWORK
    from app.core.permissions import ATWORK_PERMISSIONS, ATWORK_ROLES

    bind = op.get_bind()
    now = datetime.now(UTC)
    permissions_t = sa.table(
        "permissions",
        sa.column("key", sa.String), sa.column("name", sa.String), sa.column("description", sa.Text),
        sa.column("module_key", sa.String), sa.column("category", sa.String),
        sa.column("created_at", sa.DateTime), sa.column("updated_at", sa.DateTime),
    )
    role_permissions_t = sa.table(
        "role_permissions", sa.column("role_id", sa.Integer), sa.column("permission_id", sa.Integer),
    )

    lookup = sa.text("SELECT id FROM permissions WHERE key = :k")
    permission_ids: dict[str, int] = {}
    for perm in ATWORK_PERMISSIONS:
        if perm.key not in _NEW_KEYS:
            continue
        row = bind.execute(lookup, {"k": perm.key}).first()
        if row is None:
            op.bulk_insert(permissions_t, [{
                "key": perm.key, "name": perm.name, "description": perm.description,
                "module_key": perm.module_key, "category": perm.category,
                "created_at": now, "updated_at": now,
            }])
            row = bind.execute(lookup, {"k": perm.key}).first()
        permission_ids[perm.key] = row[0]

    for role_def in ATWORK_ROLES:
        role = bind.execute(
            sa.text("SELECT id FROM roles WHERE key = :k AND module_key = :m"), {"k": role_def.key, "m": MODULE_ATWORK}
        ).first()
        if role is None:
            continue
        existing = {
            r[0] for r in bind.execute(
                sa.text("SELECT permission_id FROM role_permissions WHERE role_id = :r"), {"r": role[0]}
            ).fetchall()
        }
        links = [
            {"role_id": role[0], "permission_id": permission_ids[k]}
            for k in role_def.permissions if k in permission_ids and permission_ids[k] not in existing
        ]
        if links:
            op.bulk_insert(role_permissions_t, links)


def downgrade() -> None:
    # Deliberately a no-op, matching the other catalog migrations.
    pass
