"""access groups (Phase 2.6)

Adds the additive access-group layer alongside direct user->module
assignment: ``access_groups``, ``user_group_memberships``,
``group_module_roles``, ``group_module_client_scopes``. Mirrors the shape
of ``user_module_roles``/``user_module_client_scopes`` — see
app/models/access_group.py. No existing table is modified. No seed data.

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-08-13 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "access_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("group_type", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("access_groups", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_access_groups_key"), ["key"], unique=True)

    op.create_table(
        "user_group_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("access_group_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["access_group_id"], ["access_groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "access_group_id", name="uq_user_group_membership"),
    )

    op.create_table(
        "group_module_roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("access_group_id", sa.Integer(), nullable=False),
        sa.Column("module_key", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["access_group_id"], ["access_groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("group_module_roles", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_group_module_roles_module_key"), ["module_key"], unique=False)

    op.create_table(
        "group_module_client_scopes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_module_role_id", sa.Integer(), nullable=False),
        # No FK to `clients` — see app/models/access_group.py.
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("all_clients", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["group_module_role_id"], ["group_module_roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("group_module_client_scopes", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_group_module_client_scopes_group_module_role_id"),
            ["group_module_role_id"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_table("group_module_client_scopes")
    with op.batch_alter_table("group_module_roles", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_group_module_roles_module_key"))
    op.drop_table("group_module_roles")
    op.drop_table("user_group_memberships")
    with op.batch_alter_table("access_groups", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_access_groups_key"))
    op.drop_table("access_groups")
