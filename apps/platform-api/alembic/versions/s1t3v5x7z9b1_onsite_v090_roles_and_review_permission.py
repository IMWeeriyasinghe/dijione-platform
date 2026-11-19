"""Diji On-site v0.9: "On-site User" label + onsite.exceptions.manage

Data migration only — no schema change, idempotent:

* relabels the ``ONSITE_VIEWER`` role (key unchanged) as "On-site User" and
  refreshes both On-site role descriptions;
* get-or-creates the ``onsite.exceptions.manage`` permission (open / justify /
  resolve / reopen attendance review cases) and links it to ``ONSITE_ADMIN``
  only. ONSITE_VIEWER never receives it.

No user, assignment, group, appointment or other module's catalog is touched.
Claims are computed from role_permissions at token issue, so On-site Admins
receive the new permission at their next sign-in/refresh; no access_version
bump is needed (it only adds a capability to an existing administrator role).
Values are inlined (not imported from app.core) so this migration never changes
meaning if the catalog is edited later. Downgrade restores the previous labels
and leaves the permission in place (removing it could orphan grants — the same
convention as the other registration migrations).

Revision ID: s1t3v5x7z9b1
Revises: r9t1v3x5z7b9
Create Date: 2026-11-19 00:00:00.000000
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "s1t3v5x7z9b1"
down_revision: str | Sequence[str] | None = "r9t1v3x5z7b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MODULE = "onsite"
PERMISSION = {
    "key": "onsite.exceptions.manage", "name": "Review Attendance Exceptions",
    "description": ("Open, justify, resolve and reopen attendance review cases (administrative records only; "
                    "fingerprint records and identity mappings are never changed)."),
    "module_key": MODULE, "category": "Attendance",
}
LABELS = {
    "ONSITE_VIEWER": ("On-site User",
                      "View the dashboard, recorded fingerprint activity, reports and attendance review cases."),
    "ONSITE_ADMIN": ("On-site Admin",
                     "On-site User permissions plus attendance review decisions, site health, identity mappings, "
                     "sync requests, site management and granting On-site User access."),
}
PREVIOUS = {
    "ONSITE_VIEWER": ("On-site Viewer", "View the dashboard, attendance activity and items needing review."),
    "ONSITE_ADMIN": ("On-site Admin",
                     "Viewer permissions plus site health, identity match report, sync requests and site management."),
}


def _relabel(labels: dict[str, tuple[str, str]]) -> None:
    bind = op.get_bind()
    for key, (name, description) in labels.items():
        bind.execute(sa.text("UPDATE roles SET name = :n, description = :d WHERE key = :k AND module_key = :m"),
                     {"n": name, "d": description, "k": key, "m": MODULE})


def upgrade() -> None:
    bind = op.get_bind()
    _relabel(LABELS)
    now = datetime.now(UTC)
    lookup = sa.text("SELECT id FROM permissions WHERE key = :k")
    row = bind.execute(lookup, {"k": PERMISSION["key"]}).first()
    if row is None:
        permissions_t = sa.table(
            "permissions",
            sa.column("key", sa.String), sa.column("name", sa.String), sa.column("description", sa.Text),
            sa.column("module_key", sa.String), sa.column("category", sa.String),
            sa.column("created_at", sa.DateTime), sa.column("updated_at", sa.DateTime),
        )
        op.bulk_insert(permissions_t, [{**PERMISSION, "created_at": now, "updated_at": now}])
        row = bind.execute(lookup, {"k": PERMISSION["key"]}).first()
    role = bind.execute(sa.text("SELECT id FROM roles WHERE key = 'ONSITE_ADMIN' AND module_key = :m"),
                        {"m": MODULE}).first()
    if role is None:  # On-site not registered in this database: nothing to link
        return
    linked = bind.execute(sa.text("SELECT 1 FROM role_permissions WHERE role_id = :r AND permission_id = :p"),
                          {"r": role[0], "p": row[0]}).first()
    if linked is None:
        role_permissions_t = sa.table("role_permissions", sa.column("role_id", sa.Integer),
                                      sa.column("permission_id", sa.Integer))
        op.bulk_insert(role_permissions_t, [{"role_id": role[0], "permission_id": row[0]}])


def downgrade() -> None:
    _relabel(PREVIOUS)
