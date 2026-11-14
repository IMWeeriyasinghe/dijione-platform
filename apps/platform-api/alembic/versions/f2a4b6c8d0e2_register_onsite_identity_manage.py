"""register onsite.identity.manage (Diji On-site Identity Management writes)

Data migration only — no schema change. Get-or-create of the
``onsite.identity.manage`` permission and its link to the ``ONSITE_ADMIN``
role, in the same idempotent style as ``i9j0k1l2m3n4_register_onsite_module``.
No other module's catalog, no user and no existing role link is touched;
ONSITE_VIEWER does not receive it.

Revision ID: f2a4b6c8d0e2
Revises: e1f3a5b7c9d0
Create Date: 2026-11-14 00:00:00.000000
"""

from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa

from alembic import op

revision: str = "f2a4b6c8d0e2"
down_revision: str | Sequence[str] | None = "e1f3a5b7c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION_KEY = "onsite.identity.manage"
ROLE_KEY = "ONSITE_ADMIN"


def upgrade() -> None:
    from app.core.constants import MODULE_ONSITE
    from app.core.permissions import ONSITE_PERMISSIONS

    perm = next(p for p in ONSITE_PERMISSIONS if p.key == PERMISSION_KEY)
    bind = op.get_bind()
    now = datetime.now(timezone.utc)
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
    row = bind.execute(lookup, {"k": PERMISSION_KEY}).first()
    if row is None:
        op.bulk_insert(permissions_t, [{
            "key": perm.key, "name": perm.name, "description": perm.description,
            "module_key": perm.module_key, "category": perm.category, "created_at": now, "updated_at": now,
        }])
        row = bind.execute(lookup, {"k": PERMISSION_KEY}).first()
    permission_id = row[0]
    role = bind.execute(
        sa.text("SELECT id FROM roles WHERE key = :k AND module_key = :m"), {"k": ROLE_KEY, "m": MODULE_ONSITE}
    ).first()
    if role is None:  # On-site not registered in this database: nothing to link
        return
    linked = bind.execute(
        sa.text("SELECT 1 FROM role_permissions WHERE role_id = :r AND permission_id = :p"),
        {"r": role[0], "p": permission_id},
    ).first()
    if linked is None:
        op.bulk_insert(role_permissions_t, [{"role_id": role[0], "permission_id": permission_id}])


def downgrade() -> None:
    # No-op like the other registration migrations: removing a permission
    # could orphan assignments. Retire it by editing the catalog instead.
    pass
