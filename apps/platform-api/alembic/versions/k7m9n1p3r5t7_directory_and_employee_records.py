"""Directory verification, employee records, and always-on default access

1. Additive columns on ``users``: ``directory_verified_at``, ``employee_number``,
   ``employee_record_status``, ``employee_record_checked_at``.
2. Compatibility: every user who holds default employee access today (active, verified internal
   Entra identity) is marked ``LEGACY`` so nobody loses access. LEGACY is a migration-only state;
   reconciliation against BambooHR later turns it into MATCHED, or reports the person for HR
   reconciliation without revoking anything.
3. Always-on default access: the per-person opt-out rows (a disabled ``user_module_roles`` row whose
   role is the module's enabled default role) are deleted. Exactly those rows: no other assignment,
   group or client-scope row is touched. Each deletion is audited, and only the affected users'
   ``access_version`` is raised. Re-running is safe.

Revision ID: k7m9n1p3r5t7
Revises: j6l8n0p2q4r5
Create Date: 2026-11-17 00:00:00.000000
"""

import json
import time
from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa

from alembic import op

revision: str = "k7m9n1p3r5t7"
down_revision: str | Sequence[str] | None = "j6l8n0p2q4r5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    ("directory_verified_at", sa.DateTime(timezone=True)),
    ("employee_number", sa.String(32)),
    ("employee_record_status", sa.String(16)),
    ("employee_record_checked_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    bind = op.get_bind()
    present = {c["name"] for c in sa.inspect(bind).get_columns("users")}
    for name, type_ in _COLUMNS:
        if name not in present:
            op.add_column("users", sa.Column(name, type_, nullable=True))

    bind.execute(
        sa.text(
            "UPDATE users SET employee_record_status = 'LEGACY' "
            "WHERE employee_record_status IS NULL AND is_active = :t AND internal_employee = :t "
            "AND identity_provider = 'ENTRA' AND entra_object_id IS NOT NULL"
        ),
        {"t": True},
    )

    exclusions = bind.execute(
        sa.text(
            "SELECT umr.id, umr.user_id, umr.module_key, umr.role FROM user_module_roles umr "
            "JOIN module_baseline_roles b ON b.module_key = umr.module_key AND b.role = umr.role "
            "WHERE umr.enabled = :f AND b.enabled = :t ORDER BY umr.id"
        ),
        {"t": True, "f": False},
    ).fetchall()
    if not exclusions:
        return
    now = datetime.now(timezone.utc)
    affected: set[int] = set()
    for row_id, user_id, module_key, role in exclusions:
        eligible = bind.execute(
            sa.text(
                "SELECT 1 FROM users WHERE id = :u AND is_active = :t AND internal_employee = :t "
                "AND identity_provider = 'ENTRA' AND entra_object_id IS NOT NULL"
            ),
            {"u": user_id, "t": True},
        ).first() is not None
        bind.execute(sa.text("DELETE FROM user_module_client_scopes WHERE user_module_role_id = :i"), {"i": row_id})
        bind.execute(sa.text("DELETE FROM user_module_roles WHERE id = :i"), {"i": row_id})
        bind.execute(
            sa.text(
                "INSERT INTO audit_logs (actor_id, action, entity_type, entity_id, previous_state, new_state, "
                "event_metadata, created_at, subject_user_id) VALUES (NULL, "
                "'module_assignment.default_access_restored', 'UserModuleRole', :i, :p, :n, :m, :c, :u)"
            ),
            {
                "i": row_id,
                "p": json.dumps({"user_id": user_id, "module_key": module_key, "role": role, "enabled": False}),
                "n": json.dumps({"module_key": module_key, "role": role, "source": "DEFAULT"}),
                "m": json.dumps({"source": "migration k7m9n1p3r5t7", "reason": "default access is always on",
                                 "eligible": eligible}),
                "c": now,
                "u": user_id,
            },
        )
        affected.add(user_id)
    for user_id in sorted(affected):
        bind.execute(
            sa.text(
                "UPDATE users SET access_version = CASE WHEN access_version + 1 > :floor "
                "THEN access_version + 1 ELSE :floor END WHERE id = :u"
            ),
            {"floor": int(time.time()), "u": user_id},
        )


def downgrade() -> None:
    # Deleted opt-out rows are not recreated (default access is always on by policy); the columns go.
    present = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("users")}
    with op.batch_alter_table("users") as batch:
        for name, _type in reversed(_COLUMNS):
            if name in present:
                batch.drop_column(name)
