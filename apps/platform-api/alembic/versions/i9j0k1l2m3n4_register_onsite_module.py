"""register the Diji On-site module (catalog + module registry rows)

Data migration only — no schema change. Get-or-create of the ``onsite``
permissions, roles, role->permission links and its ``application_modules``
row, in the same idempotent style as ``f6a7b8c9d0e1_seed_authorization_catalog``
(and converging with ``scripts/seed.py``). Only rows whose ``module_key`` is
``onsite`` are touched; every other module's catalog is left exactly as is.

Platform Core only stores this registration so it can resolve On-site roles
into signed JWT claims and list the module; it never calls onsite-api.
Removing Diji On-site later means disabling the registry row (Admin Center),
not reverting this migration — see docs/onsite/module-removal.md.

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-10-22 00:00:00.000000
"""

from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "i9j0k1l2m3n4"
down_revision: Union[str, Sequence[str], None] = "h8i9j0k1l2m3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ONSITE_MODULE_ROW = dict(
    key="onsite", name="Diji On-site",
    description="On-site Attendance Operations", icon="MapPin",
    route="/onsite", status="COMING_SOON", enabled=True,
    display_order=4, required_roles="ANY",
)


def upgrade() -> None:
    # Imported here, not at module scope — same convention as
    # f6a7b8c9d0e1 (history/heads listings never need the app importable).
    from app.core.constants import MODULE_ONSITE
    from app.core.permissions import ONSITE_PERMISSIONS, ONSITE_ROLES

    bind = op.get_bind()
    now = datetime.now(timezone.utc)

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
        sa.column("required_roles", sa.String),
        sa.column("created_at", sa.DateTime), sa.column("updated_at", sa.DateTime),
    )

    perm_lookup = sa.text("SELECT id FROM permissions WHERE key = :k")
    permission_ids: dict[str, int] = {}
    for perm in ONSITE_PERMISSIONS:
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
    for role_def in ONSITE_ROLES:
        params = {"k": role_def.key, "m": MODULE_ONSITE}
        row = bind.execute(role_lookup, params).first()
        if row is None:
            op.bulk_insert(roles_t, [{
                "module_key": MODULE_ONSITE, "key": role_def.key, "name": role_def.name,
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
        sa.text("SELECT id FROM application_modules WHERE key = :k"), {"k": ONSITE_MODULE_ROW["key"]}
    ).first()
    if row is None:
        op.bulk_insert(modules_t, [{**ONSITE_MODULE_ROW, "created_at": now, "updated_at": now}])
    # An existing row is left untouched: once registered, its status/enabled
    # flag is managed by platform admins (e.g. disabled on module removal).


def downgrade() -> None:
    # Deliberately a no-op, matching f6a7b8c9d0e1: deleting catalog rows
    # would orphan any UserModuleRole/GroupModuleRole assignments that
    # reference them. Module removal is done by disabling the registry row.
    pass
