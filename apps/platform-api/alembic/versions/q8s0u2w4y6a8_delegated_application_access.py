"""Delegated application access administration

1. Two additive tables: ``application_administrators`` (a Super Admin's appointment of an
   application's access administrator, with explicit authority) and
   ``application_access_suspensions`` (an application-scoped deny).
2. Catalogue: for DijiTalentFlow, DIJI Birthday, Diji On-site and DijiAtWork, the
   ``<app>.access.manage`` / ``<app>.access.manage_admins`` permissions and the two
   administrator-only roles that carry them. Get-or-create, so it is idempotent and safe on a
   database whose catalogue was seeded from the current code.

Nothing existing changes: no assignment, group, scope or user row is touched. No access_version
bump is needed (deliberately, so nobody's session is revoked): the new roles are held by nobody and
the new tables start empty, so no one's effective access differs after this migration. Appointments
and suspensions are made later through the ORM, where the listener bumps exactly the people affected.

Downgrade is GUARDED. While any appointment or suspension exists it refuses: dropping a suspension
would silently give the suspended people their group access back. Remove them deliberately first
(see docs/platform/delegated-access.md, "Rollback"). Catalogue rows are kept on downgrade, like
every other registration migration here; they are inert without the tables.

Revision ID: q8s0u2w4y6a8
Revises: k7m9n1p3r5t7
Create Date: 2026-11-18 00:00:00.000000
"""

from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa

from alembic import op

revision: str = "q8s0u2w4y6a8"
down_revision: str | Sequence[str] | None = "k7m9n1p3r5t7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "application_administrators" not in tables:
        op.create_table(
            "application_administrators",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("module_key", sa.String(64), nullable=False),
            sa.Column("grantable_roles", sa.JSON(), nullable=False),
            sa.Column("client_authority", sa.JSON(), nullable=True),
            sa.Column("can_appoint_admins", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column(
                "appointed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
            ),
            *_timestamps(),
            sa.UniqueConstraint("user_id", "module_key", name="uq_application_administrators_user_module"),
        )
        op.create_index("ix_application_administrators_user_id", "application_administrators", ["user_id"])
        op.create_index("ix_application_administrators_module_key", "application_administrators", ["module_key"])
    if "application_access_suspensions" not in tables:
        op.create_table(
            "application_access_suspensions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("module_key", sa.String(64), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "suspended_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
            ),
            *_timestamps(),
            sa.UniqueConstraint("user_id", "module_key", name="uq_application_access_suspensions_user_module"),
        )
        op.create_index("ix_application_access_suspensions_user_id", "application_access_suspensions", ["user_id"])
        op.create_index(
            "ix_application_access_suspensions_module_key", "application_access_suspensions", ["module_key"]
        )

    _register_catalog(bind)


def _register_catalog(bind) -> None:
    from app.core.permissions import ACCESS_PERMISSIONS, ACCESS_ROLES

    now = datetime.now(timezone.utc)
    perm_id = sa.text("SELECT id FROM permissions WHERE key = :k")
    for perm in ACCESS_PERMISSIONS:
        if bind.execute(perm_id, {"k": perm.key}).first() is None:
            bind.execute(
                sa.text(
                    "INSERT INTO permissions (key, name, description, module_key, category, created_at, updated_at) "
                    "VALUES (:k, :n, :d, :m, :c, :t, :t)"
                ),
                {"k": perm.key, "n": perm.name, "d": perm.description, "m": perm.module_key, "c": perm.category,
                 "t": now},
            )
    role_id = sa.text("SELECT id FROM roles WHERE key = :k AND module_key = :m")
    for role in ACCESS_ROLES:
        row = bind.execute(role_id, {"k": role.key, "m": role.module_key}).first()
        if row is None:
            bind.execute(
                sa.text(
                    "INSERT INTO roles (key, name, description, module_key, is_system, created_at, updated_at) "
                    "VALUES (:k, :n, :d, :m, :s, :t, :t)"
                ),
                {"k": role.key, "n": role.name, "d": role.description, "m": role.module_key, "s": True, "t": now},
            )
            row = bind.execute(role_id, {"k": role.key, "m": role.module_key}).first()
        for key in role.permissions:
            pid = bind.execute(perm_id, {"k": key}).scalar_one()
            linked = bind.execute(
                sa.text("SELECT 1 FROM role_permissions WHERE role_id = :r AND permission_id = :p"),
                {"r": row[0], "p": pid},
            ).first()
            if linked is None:
                bind.execute(
                    sa.text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:r, :p)"),
                    {"r": row[0], "p": pid},
                )


class DowngradeRefused(RuntimeError):
    pass


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    counts = {
        name: bind.execute(sa.text(f"SELECT COUNT(*) FROM {name}")).scalar()
        for name in ("application_administrators", "application_access_suspensions")
        if name in tables
    }
    if any(counts.values()):
        raise DowngradeRefused(
            "Refusing to downgrade: "
            + ", ".join(f"{n}={c}" for n, c in counts.items())
            + ". Dropping these would silently restore access removed by application suspensions. "
            "Remove appointments and suspensions deliberately first (docs/platform/delegated-access.md, Rollback)."
        )
    for name in ("application_access_suspensions", "application_administrators"):
        if name in tables:
            op.drop_table(name)
