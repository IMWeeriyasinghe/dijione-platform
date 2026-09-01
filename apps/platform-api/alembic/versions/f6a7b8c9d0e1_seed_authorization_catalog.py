"""seed the role/permission/module_registry catalog

Architecture Completion Plan Wave G — closes a real gap the audit found
(DijiOne-DijiTalentFlow-Audit-2026-08-31.md P0-4): ``app.core.permissions``'s
own docstring has long claimed "Both the Alembic migration (one-time
backfill) and scripts/seed.py ... import this module so the two never
drift" — but no such migration existed. A freshly-migrated (not
``scripts/seed.py --reset``-seeded) database had zero rows in
``permissions``/``roles``/``role_permissions``/``application_modules``,
making the Admin Center and the module registry unusable out of the box —
exactly the scenario a first Azure DEV boot goes through before anyone runs
a seed script by hand.

Idempotent get-or-create, safe to run against a DB that ``scripts/seed.py``
already populated (matches its own get-or-create / converge semantics for
``application_modules`` — CI dev DBs seeded by the script are unaffected)
and against a bare freshly-migrated DB (the actual gap this closes).

Revision ID: f6a7b8c9d0e1
Revises: d4e5f6a7b8c9
Create Date: 2026-09-01 00:00:00.000000
"""

from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Imported here, not at module scope, so a plain `alembic history`/
    # `alembic heads` listing never needs the app package importable —
    # only actually running this migration does (same convention env.py
    # already relies on via sys.path.insert).
    from app.core.constants import MODULE_BIRTHDAY, MODULE_SPARK, MODULE_TALENT_FLOW
    from app.core.permissions import ALL_PERMISSIONS, ALL_ROLES

    bind = op.get_bind()
    now = datetime.now(timezone.utc)

    permissions_t = sa.table(
        "permissions",
        sa.column("id", sa.Integer),
        sa.column("key", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("module_key", sa.String),
        sa.column("category", sa.String),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    roles_t = sa.table(
        "roles",
        sa.column("id", sa.Integer),
        sa.column("module_key", sa.String),
        sa.column("key", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("is_system", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    role_permissions_t = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Integer),
        sa.column("permission_id", sa.Integer),
    )
    modules_t = sa.table(
        "application_modules",
        sa.column("id", sa.Integer),
        sa.column("key", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("icon", sa.String),
        sa.column("route", sa.String),
        sa.column("status", sa.String),
        sa.column("enabled", sa.Boolean),
        sa.column("display_order", sa.Integer),
        sa.column("required_roles", sa.String),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )

    # --- permissions --------------------------------------------------
    permission_ids: dict[str, int] = {}
    for perm in ALL_PERMISSIONS:
        row = bind.execute(
            sa.text("SELECT id FROM permissions WHERE key = :k"), {"k": perm.key}
        ).first()
        if row is None:
            op.bulk_insert(
                permissions_t,
                [{
                    "key": perm.key, "name": perm.name, "description": perm.description,
                    "module_key": perm.module_key, "category": perm.category,
                    "created_at": now, "updated_at": now,
                }],
            )
            row = bind.execute(
                sa.text("SELECT id FROM permissions WHERE key = :k"), {"k": perm.key}
            ).first()
        permission_ids[perm.key] = row[0]

    # --- roles + role_permissions --------------------------------------
    # `:m` (module_key) is legitimately NULL for platform-wide roles
    # (SUPER_ADMIN etc.) — reusing the same bind param both against `IS
    # NULL` and in an equality comparison leaves Postgres's extended-query
    # protocol unable to infer its type ("could not determine data type of
    # parameter"), even though SQLite never minded. Explicit `bindparam`
    # typing fixes it on both dialects — verified against a real
    # postgres:16 CI run, not just SQLite.
    role_lookup = sa.text(
        "SELECT id FROM roles WHERE key = :k AND "
        "((module_key IS NULL AND :m IS NULL) OR module_key = :m)"
    ).bindparams(sa.bindparam("k", type_=sa.String), sa.bindparam("m", type_=sa.String))

    for role_def in ALL_ROLES:
        params = {"k": role_def.key, "m": role_def.module_key}
        row = bind.execute(role_lookup, params).first()
        if row is None:
            op.bulk_insert(
                roles_t,
                [{
                    "module_key": role_def.module_key, "key": role_def.key,
                    "name": role_def.name, "description": role_def.description,
                    "is_system": True, "created_at": now, "updated_at": now,
                }],
            )
            row = bind.execute(role_lookup, params).first()
        role_id = row[0]

        existing_perm_ids = {
            r[0]
            for r in bind.execute(
                sa.text("SELECT permission_id FROM role_permissions WHERE role_id = :r"),
                {"r": role_id},
            ).fetchall()
        }
        new_links = [
            {"role_id": role_id, "permission_id": permission_ids[perm_key]}
            for perm_key in role_def.permissions
            if permission_ids[perm_key] not in existing_perm_ids
        ]
        if new_links:
            op.bulk_insert(role_permissions_t, new_links)

    # --- application_modules (get-or-create + converge, mirrors
    # scripts/seed.py's seed_module_registry) ---------------------------
    module_definitions = [
        dict(
            key=MODULE_TALENT_FLOW, name="DijiTalentFlow",
            description="Talent Operations and Client Tracking", icon="Users",
            route="/talent-flow", status="ACTIVE", enabled=True,
            display_order=1, required_roles="ANY",
        ),
        dict(
            key=MODULE_BIRTHDAY, name="DijiBirthday",
            description="Birthday Workflow Automation", icon="Cake",
            route="/birthday", status="ACTIVE", enabled=True,
            display_order=2, required_roles="ANY",
        ),
        dict(
            key=MODULE_SPARK, name="DijiSpark",
            description="HR / Spark Hire Workflows", icon="Sparkles",
            route="/spark", status="COMING_SOON", enabled=True,
            display_order=3, required_roles="",
        ),
    ]
    for fields in module_definitions:
        row = bind.execute(
            sa.text("SELECT id FROM application_modules WHERE key = :k"), {"k": fields["key"]}
        ).first()
        if row is None:
            op.bulk_insert(modules_t, [{**fields, "created_at": now, "updated_at": now}])
        else:
            set_clause = ", ".join(f"{col} = :{col}" for col in fields if col != "key")
            bind.execute(
                sa.text(f"UPDATE application_modules SET {set_clause} WHERE key = :key"),
                {**fields, "updated_at": now},
            )


def downgrade() -> None:
    # Deliberately a no-op: this migration only ever inserts/updates rows
    # that scripts/seed.py would also converge to, or that were already
    # correct. Deleting the catalog on downgrade would break every existing
    # role/permission/module assignment referencing it (RolePermission,
    # UserModuleRole.module_key, ApplicationModule) for no safety benefit —
    # there is nothing destructive in `upgrade()` to undo.
    pass
