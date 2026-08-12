"""DijiOne Phase 2 authorization model

Adds the centralized Role / Permission / RolePermission catalog,
UserModuleClientScope (client/portfolio scope), an ``enabled`` flag on
module assignments, and DijiOne Phase 2 identity fields on ``users``
(entra_object_id, identity_provider, last_login_at).

Backfills:
  - the full Role/Permission/RolePermission catalog from
    ``app.core.permissions`` (single source of truth, also used by
    ``scripts/seed.py``);
  - a UserModuleClientScope row for every existing UserModuleRole, so
    pre-Phase-2 data keeps working unchanged: TALENT_CLIENT rows get a
    single client-scoped row, staff rows get an ``all_clients`` row
    (preserving their existing unrestricted cross-client access).

Revision ID: 2e7f7d7dc3fa
Revises: 7fc14b916a0e
Create Date: 2026-08-12 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2e7f7d7dc3fa"
down_revision: Union[str, Sequence[str], None] = "7fc14b916a0e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- New columns -------------------------------------------------
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("entra_object_id", sa.String(length=128), nullable=True))
        batch_op.add_column(
            sa.Column(
                "identity_provider", sa.String(length=32), nullable=False,
                server_default="DEV_IDENTITY",
            )
        )
        batch_op.add_column(sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_unique_constraint("uq_users_entra_object_id", ["entra_object_id"])

    with op.batch_alter_table("user_module_roles", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true())
        )

    # --- New tables ----------------------------------------------------
    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("module_key", sa.String(length=64), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_permissions_key"),
    )
    with op.batch_alter_table("permissions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_permissions_key"), ["key"], unique=False)
        batch_op.create_index(batch_op.f("ix_permissions_module_key"), ["module_key"], unique=False)

    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("module_key", sa.String(length=64), nullable=True),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("module_key", "key", name="uq_roles_module_key"),
    )
    with op.batch_alter_table("roles", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_roles_module_key"), ["module_key"], unique=False)
        batch_op.create_index(batch_op.f("ix_roles_key"), ["key"], unique=False)

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )

    op.create_table(
        "user_module_client_scopes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_module_role_id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("all_clients", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["user_module_role_id"], ["user_module_roles.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("user_module_client_scopes", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_user_module_client_scopes_user_module_role_id"),
            ["user_module_role_id"],
            unique=False,
        )

    _backfill(op.get_bind())


def _backfill(bind: sa.engine.Connection) -> None:
    from datetime import UTC, datetime

    from app.core.permissions import ALL_PERMISSIONS, ALL_ROLES

    now = datetime.now(UTC)
    meta = sa.MetaData()
    permissions_t = sa.Table("permissions", meta, autoload_with=bind)
    roles_t = sa.Table("roles", meta, autoload_with=bind)
    role_permissions_t = sa.Table("role_permissions", meta, autoload_with=bind)
    user_module_roles_t = sa.Table("user_module_roles", meta, autoload_with=bind)
    scopes_t = sa.Table("user_module_client_scopes", meta, autoload_with=bind)

    permission_ids: dict[str, int] = {}
    for perm in ALL_PERMISSIONS:
        result = bind.execute(
            permissions_t.insert().values(
                key=perm.key, name=perm.name, description=perm.description,
                module_key=perm.module_key, category=perm.category,
                created_at=now, updated_at=now,
            )
        )
        permission_ids[perm.key] = result.inserted_primary_key[0]

    for role in ALL_ROLES:
        result = bind.execute(
            roles_t.insert().values(
                module_key=role.module_key, key=role.key, name=role.name,
                description=role.description, is_system=True,
                created_at=now, updated_at=now,
            )
        )
        role_id = result.inserted_primary_key[0]
        for perm_key in role.permissions:
            bind.execute(
                role_permissions_t.insert().values(
                    role_id=role_id, permission_id=permission_ids[perm_key]
                )
            )

    # Backfill scope rows for every existing module assignment so current
    # demo personas and any hand-created rows keep exactly their pre-Phase-2
    # access: TALENT_CLIENT -> single client scope; staff -> all_clients.
    existing_assignments = bind.execute(sa.select(user_module_roles_t)).mappings().all()
    for row in existing_assignments:
        if row["client_id"] is not None:
            bind.execute(
                scopes_t.insert().values(
                    user_module_role_id=row["id"], client_id=row["client_id"],
                    all_clients=False, created_at=now, updated_at=now,
                )
            )
        else:
            bind.execute(
                scopes_t.insert().values(
                    user_module_role_id=row["id"], client_id=None,
                    all_clients=True, created_at=now, updated_at=now,
                )
            )


def downgrade() -> None:
    op.drop_table("user_module_client_scopes")
    op.drop_table("role_permissions")
    with op.batch_alter_table("roles", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_roles_key"))
        batch_op.drop_index(batch_op.f("ix_roles_module_key"))
    op.drop_table("roles")
    with op.batch_alter_table("permissions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_permissions_module_key"))
        batch_op.drop_index(batch_op.f("ix_permissions_key"))
    op.drop_table("permissions")

    with op.batch_alter_table("user_module_roles", schema=None) as batch_op:
        batch_op.drop_column("enabled")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint("uq_users_entra_object_id", type_="unique")
        batch_op.drop_column("last_login_at")
        batch_op.drop_column("identity_provider")
        batch_op.drop_column("entra_object_id")
