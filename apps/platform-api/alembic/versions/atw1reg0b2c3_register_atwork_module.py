"""register the DijiAtWork module (catalog + module registry rows)

Data migration only — no schema change. Get-or-create of the ``atwork``
permissions, roles, role->permission links and its ``application_modules``
row, in the same idempotent style as ``i9j0k1l2m3n4``. Only DijiAtWork rows are
touched. The module stays ``COMING_SOON``; this never activates it.

Removing DijiAtWork means disabling the registry row, not reverting this
migration — see docs/atwork/module-removal.md.

Revision ID: atw1reg0b2c3
Revises: m3n4o5p6q7r8
Create Date: 2026-11-09 00:00:00.000000
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "atw1reg0b2c3"
down_revision: str | Sequence[str] | None = "m3n4o5p6q7r8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ATWORK_MODULE_ROW = dict(
    key="atwork", name="DijiAtWork",
    description="Work Check-in and Attendance", icon="Clock",
    route="/atwork", status="COMING_SOON", enabled=True,
    display_order=5, required_roles="ANY", supports_client_scope=False,
)


def upgrade() -> None:
    # Imported here, not at module scope — same convention as i9j0k1l2m3n4
    # (history/heads listings never need the app importable).
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
    roles_t = sa.table(
        "roles",
        sa.column("module_key", sa.String), sa.column("key", sa.String), sa.column("name", sa.String),
        sa.column("description", sa.Text), sa.column("is_system", sa.Boolean),
        sa.column("created_at", sa.DateTime), sa.column("updated_at", sa.DateTime),
    )
    role_permissions_t = sa.table(
        "role_permissions", sa.column("role_id", sa.Integer), sa.column("permission_id", sa.Integer),
    )
    modules_t = sa.table(
        "application_modules",
        sa.column("key", sa.String), sa.column("name", sa.String), sa.column("description", sa.Text),
        sa.column("icon", sa.String), sa.column("route", sa.String), sa.column("status", sa.String),
        sa.column("enabled", sa.Boolean), sa.column("display_order", sa.Integer),
        sa.column("required_roles", sa.String), sa.column("supports_client_scope", sa.Boolean),
        sa.column("created_at", sa.DateTime), sa.column("updated_at", sa.DateTime),
    )

    perm_lookup = sa.text("SELECT id FROM permissions WHERE key = :k")
    permission_ids: dict[str, int] = {}
    for perm in ATWORK_PERMISSIONS:
        row = bind.execute(perm_lookup, {"k": perm.key}).first()
        if row is None:
            op.bulk_insert(permissions_t, [{
                "key": perm.key, "name": perm.name, "description": perm.description,
                "module_key": perm.module_key, "category": perm.category,
                "created_at": now, "updated_at": now,
            }])
            row = bind.execute(perm_lookup, {"k": perm.key}).first()
        permission_ids[perm.key] = row[0]

    role_lookup = sa.text("SELECT id FROM roles WHERE key = :k AND module_key = :m").bindparams(
        sa.bindparam("k", type_=sa.String), sa.bindparam("m", type_=sa.String)
    )
    for role_def in ATWORK_ROLES:
        params = {"k": role_def.key, "m": MODULE_ATWORK}
        row = bind.execute(role_lookup, params).first()
        if row is None:
            op.bulk_insert(roles_t, [{
                "module_key": MODULE_ATWORK, "key": role_def.key, "name": role_def.name,
                "description": role_def.description, "is_system": True,
                "created_at": now, "updated_at": now,
            }])
            row = bind.execute(role_lookup, params).first()
        role_id = row[0]
        existing = {
            r[0] for r in bind.execute(
                sa.text("SELECT permission_id FROM role_permissions WHERE role_id = :r"), {"r": role_id}
            ).fetchall()
        }
        links = [
            {"role_id": role_id, "permission_id": permission_ids[k]}
            for k in role_def.permissions if permission_ids[k] not in existing
        ]
        if links:
            op.bulk_insert(role_permissions_t, links)

    row = bind.execute(
        sa.text("SELECT id FROM application_modules WHERE key = :k"), {"k": ATWORK_MODULE_ROW["key"]}
    ).first()
    if row is None:
        op.bulk_insert(modules_t, [{**ATWORK_MODULE_ROW, "created_at": now, "updated_at": now}])
    # An existing row is left untouched: its status and enabled flag are
    # managed by platform admins once registered.


def downgrade() -> None:
    # Deliberately a no-op: deleting catalog rows would orphan assignments.
    pass
