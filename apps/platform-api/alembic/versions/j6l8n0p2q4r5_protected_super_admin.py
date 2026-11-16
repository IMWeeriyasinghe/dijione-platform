"""Protected Super Admin: the policy table and the initial grant

Additive. Creates ``protected_admins`` and registers the protected administrator identified by
e-mail address. If that person already has a DijiOne account the migration sets the platform role
to SUPER_ADMIN (the existing role; no new role is introduced), records the Entra identity the
account is already bound to, raises that one user's ``access_version`` so a new session carries
the permissions, and writes one audit entry. Application assignments, groups, client scopes and
identity fields are not touched. If the account does not exist yet nothing else changes, and the
role is applied the first time that person signs in (see ``protected_admin.converge``).
Re-running is safe.

Revision ID: j6l8n0p2q4r5
Revises: i5k7m9n1p3q4
Create Date: 2026-11-17 00:00:00.000000
"""

import json
import time
from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa

from alembic import op

revision: str = "j6l8n0p2q4r5"
down_revision: str | Sequence[str] | None = "i5k7m9n1p3q4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROTECTED_EMAIL = "madushanka.weeriyasinghe@dijitalteam.com"
ROLE = "SUPER_ADMIN"


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(timezone.utc)
    if not sa.inspect(bind).has_table("protected_admins"):
        op.create_table(
            "protected_admins",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("entra_object_id", sa.String(128), nullable=True),
            sa.Column("required_role", sa.String(32), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_protected_admins_email", "protected_admins", ["email"], unique=True)
        op.create_index("ix_protected_admins_entra_object_id", "protected_admins", ["entra_object_id"], unique=True)

    user = bind.execute(
        sa.text("SELECT id, platform_role, entra_object_id FROM users WHERE lower(email) = :e"), {"e": PROTECTED_EMAIL}
    ).fetchall()
    if len(user) > 1:
        raise RuntimeError("More than one account matches the protected administrator's e-mail address")
    oid = user[0][2] if user else None

    if bind.execute(sa.text("SELECT 1 FROM protected_admins WHERE email = :e"), {"e": PROTECTED_EMAIL}).first() is None:
        bind.execute(
            sa.text(
                "INSERT INTO protected_admins (email, entra_object_id, required_role, created_at, updated_at) "
                "VALUES (:e, :o, :r, :n, :n)"
            ),
            {"e": PROTECTED_EMAIL, "o": oid, "r": ROLE, "n": now},
        )

    if user and user[0][1] != ROLE:
        uid, previous = user[0][0], user[0][1]
        bind.execute(sa.text("UPDATE users SET platform_role = :r, is_active = :a WHERE id = :i"), {"r": ROLE, "a": True, "i": uid})
        bind.execute(
            sa.text(
                "UPDATE users SET access_version = CASE WHEN access_version + 1 > :floor "
                "THEN access_version + 1 ELSE :floor END WHERE id = :i"
            ),
            {"floor": int(time.time()), "i": uid},
        )
        bind.execute(
            sa.text(
                "INSERT INTO audit_logs (actor_id, action, entity_type, entity_id, previous_state, new_state, "
                "event_metadata, created_at, subject_user_id) "
                "VALUES (NULL, 'user.platform_role_changed', 'User', :i, :p, :n, :m, :t, :i)"
            ),
            {
                "i": uid,
                "p": json.dumps({"platform_role": previous}),
                "n": json.dumps({"platform_role": ROLE}),
                "m": json.dumps({"source": "migration j6l8n0p2q4r5", "reason": "protected super admin initial grant"}),
                "t": now,
            },
        )


def downgrade() -> None:
    # The grant is deliberately kept: removing the table lifts the protection, not the role.
    if sa.inspect(op.get_bind()).has_table("protected_admins"):
        op.drop_table("protected_admins")
