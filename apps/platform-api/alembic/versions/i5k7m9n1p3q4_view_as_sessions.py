"""View-as: the sessions table and the platform.admin.view_as permission

Additive. Creates ``view_as_sessions``, registers the ``platform.admin.view_as`` permission, links
it to the SUPER_ADMIN role only (PLATFORM_ADMIN does not receive it), and raises every user's
``access_version`` so sessions issued before the new permission existed are re-issued with it.
Nothing is removed and no existing role link is touched. Re-running is safe.

Revision ID: i5k7m9n1p3q4
Revises: h4j6k8m0n2p3
Create Date: 2026-11-16 00:00:00.000000
"""

import time
from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa

from alembic import op

revision: str = "i5k7m9n1p3q4"
down_revision: str | Sequence[str] | None = "h4j6k8m0n2p3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION_KEY = "platform.admin.view_as"
ROLE_KEY = "SUPER_ADMIN"


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("view_as_sessions"):
        op.create_table(
            "view_as_sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("public_id", sa.String(36), nullable=False),
            sa.Column("admin_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("target_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("end_reason", sa.String(32), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_view_as_sessions_public_id", "view_as_sessions", ["public_id"], unique=True)
        op.create_index("ix_view_as_sessions_admin_user_id", "view_as_sessions", ["admin_user_id"])
        op.create_index("ix_view_as_sessions_target_user_id", "view_as_sessions", ["target_user_id"])

    from app.core.permissions import PLATFORM_PERMISSIONS

    perm = next(p for p in PLATFORM_PERMISSIONS if p.key == PERMISSION_KEY)
    now = datetime.now(timezone.utc)
    lookup = sa.text("SELECT id FROM permissions WHERE key = :k")
    row = bind.execute(lookup, {"k": PERMISSION_KEY}).first()
    if row is None:
        op.bulk_insert(
            sa.table(
                "permissions",
                sa.column("key", sa.String), sa.column("name", sa.String), sa.column("description", sa.Text),
                sa.column("module_key", sa.String), sa.column("category", sa.String),
                sa.column("created_at", sa.DateTime), sa.column("updated_at", sa.DateTime),
            ),
            [{
                "key": perm.key, "name": perm.name, "description": perm.description, "module_key": None,
                "category": perm.category, "created_at": now, "updated_at": now,
            }],
        )
        row = bind.execute(lookup, {"k": PERMISSION_KEY}).first()
    role = bind.execute(sa.text("SELECT id FROM roles WHERE key = :k AND module_key IS NULL"), {"k": ROLE_KEY}).first()
    if role is not None:
        linked = bind.execute(
            sa.text("SELECT 1 FROM role_permissions WHERE role_id = :r AND permission_id = :p"),
            {"r": role[0], "p": row[0]},
        ).first()
        if linked is None:
            op.bulk_insert(
                sa.table("role_permissions", sa.column("role_id", sa.Integer), sa.column("permission_id", sa.Integer)),
                [{"role_id": role[0], "permission_id": row[0]}],
            )

    # A new permission changes what a SUPER_ADMIN's session should carry: raise every version
    # (max(old + 1, now), the same rule the application uses, see app/services/access_version.py).
    bind.execute(
        sa.text(
            "UPDATE users SET access_version = CASE WHEN access_version + 1 > :floor "
            "THEN access_version + 1 ELSE :floor END"
        ),
        {"floor": int(time.time())},
    )


def downgrade() -> None:
    # The permission link is kept, like the other registration migrations (removing it could orphan
    # grants); only the table goes.
    if sa.inspect(op.get_bind()).has_table("view_as_sessions"):
        op.drop_table("view_as_sessions")
