"""platform-api initial schema

Phase 2.5 service separation: platform.db owns identity, authorization, the
module registry, audit log and notifications only — DijiTalentFlow's
Client/TalentRequest/etc. tables live in talent-api's own database now, so
``user_module_roles.client_id`` and ``user_module_client_scopes.client_id``
carry no foreign key (cross-service references are opaque ids — see
app/models/user.py). This is a fresh combined schema (equivalent to the
pre-split apps/api's two migrations minus every talent-owned table), not an
incremental migration, since this is a new service with no prior data.

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-08-13 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "application_modules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("icon", sa.String(length=64), nullable=False),
        sa.Column("route", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("required_roles", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("application_modules", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_application_modules_key"), ["key"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("platform_role", sa.String(length=32), nullable=False),
        sa.Column("persona_key", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("avatar_color", sa.String(length=16), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("entra_object_id", sa.String(length=128), nullable=True),
        sa.Column("identity_provider", sa.String(length=32), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("persona_key"),
        sa.UniqueConstraint("entra_object_id", name="uq_users_entra_object_id"),
    )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_users_email"), ["email"], unique=True)

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
        "user_module_roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("module_key", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        # No FK to a `clients` table — Client is owned by talent-api's own
        # database. See app/models/user.py.
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("user_module_roles", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_user_module_roles_client_id"), ["client_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_user_module_roles_module_key"), ["module_key"], unique=False)

    op.create_table(
        "user_module_client_scopes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_module_role_id", sa.Integer(), nullable=False),
        # No FK to `clients` — see note above.
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("all_clients", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_module_role_id"], ["user_module_roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("user_module_client_scopes", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_user_module_client_scopes_user_module_role_id"),
            ["user_module_role_id"],
            unique=False,
        )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("previous_state", sa.Text(), nullable=False),
        sa.Column("new_state", sa.Text(), nullable=False),
        sa.Column("event_metadata", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("related_entity_type", sa.String(length=64), nullable=True),
        sa.Column("related_entity_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_notifications_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("audit_logs")
    op.drop_table("user_module_client_scopes")
    op.drop_table("user_module_roles")
    op.drop_table("role_permissions")
    with op.batch_alter_table("roles", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_roles_key"))
        batch_op.drop_index(batch_op.f("ix_roles_module_key"))
    op.drop_table("roles")
    with op.batch_alter_table("permissions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_permissions_module_key"))
        batch_op.drop_index(batch_op.f("ix_permissions_key"))
    op.drop_table("permissions")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_email"))
    op.drop_table("users")
    with op.batch_alter_table("application_modules", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_application_modules_key"))
    op.drop_table("application_modules")
