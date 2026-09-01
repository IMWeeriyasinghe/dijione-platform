"""reconcile the canonical Client master onto real, DTC-verified clients

Architecture Completion Plan — real-data local validation (2026-09-01).
The previous canonical Client set (ABC Company / XYZ Company / Nova
Solutions, seeded by ``d4e5f6a7b8c9``) was demo/fixture data invented for
the MVP, not real clients. This migration replaces it with the real,
currently-active client set discovered by a live, GET-only Recruitment
Source sync against the production Lever tenant and the governed
``DTC - <Client Name>`` tag (see ``app.core.real_dev_clients`` for the full
discovery record and ``docs/integrations/lever.md``): 649 postings read,
32 carrying a valid DTC tag, 28 distinct client names, 0 malformed/
ambiguous cases — no fuzzy matching, no invented names, every one an exact
``parse_dtc()`` "OK" result.

- Inserts the 28 real ``Client`` rows (idempotent get-or-create, same
  pattern as ``d4e5f6a7b8c9``/``f6a7b8c9d0e1``).
- Removes the 3 demo ``Client`` rows and everything that only existed to
  reference them: their ``client_external_ids`` crosswalk rows, and any
  ``user_module_client_scopes``/``user_module_roles`` rows whose
  ``client_ref`` pointed at a demo client (these were the ``abc-client``/
  ``xyz-client``/``nova-client`` dev personas' TALENT_CLIENT bindings —
  ``scripts/seed.py`` recreates them pointing at real clients on next
  run). Nothing about the RBAC catalog, module registry, or any non-client
  user/role/permission data is touched.

Talent-api's own ``clients`` table (its TalentFlow-owned extension, keyed
on ``platform_client_id``) is a separate service/database — this migration
cannot and does not touch it; ``apps/talent-api``'s own reset path handles
reconciling its extension rows to the new platform client set.

Revision ID: h8i9j0k1l2m3
Revises: f6a7b8c9d0e1
Create Date: 2026-09-01 00:00:00.000000
"""

from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "h8i9j0k1l2m3"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEMO_CLIENT_PUBLIC_IDS = ["cli-abc-company", "cli-xyz-company", "cli-nova-solutions"]


def upgrade() -> None:
    # Imported here (not module scope) for the same reason
    # f6a7b8c9d0e1 does — only running this migration needs the app
    # package importable, not a plain `alembic history`/`heads` listing.
    from app.core.real_dev_clients import REAL_DEV_CLIENTS

    bind = op.get_bind()
    now = datetime.now(timezone.utc)

    clients_t = sa.table(
        "clients",
        sa.column("id", sa.Integer),
        sa.column("public_id", sa.String),
        sa.column("name", sa.String),
        sa.column("status", sa.String),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )

    # --- insert the real clients (idempotent) --------------------------
    for real_client in REAL_DEV_CLIENTS:
        existing = bind.execute(
            sa.text("SELECT id FROM clients WHERE public_id = :p"), {"p": real_client.public_id}
        ).first()
        if existing is None:
            op.bulk_insert(
                clients_t,
                [{
                    "public_id": real_client.public_id, "name": real_client.name,
                    "status": "ACTIVE", "created_at": now, "updated_at": now,
                }],
            )

    # --- remove the demo clients + everything that only referenced them
    for demo_public_id in _DEMO_CLIENT_PUBLIC_IDS:
        row = bind.execute(
            sa.text("SELECT id FROM clients WHERE public_id = :p"), {"p": demo_public_id}
        ).first()
        if row is None:
            continue
        demo_client_id = row[0]

        # user_module_client_scopes reference a demo client two independent
        # ways: (a) via their parent role's client_ref (a role scoped to
        # exactly one client), and (b) directly on the scope row itself
        # (a portfolio role — role.client_ref is NULL, but each scope
        # child carries its own client_ref, one row per client in the
        # portfolio). Both must be deleted before the role rows themselves,
        # or (b) rows are silently orphaned (client_ref is a plain indexed
        # String, not a real FK — SQLite raises nothing).
        bind.execute(
            sa.text("DELETE FROM user_module_client_scopes WHERE client_ref = :ref"),
            {"ref": demo_public_id},
        )
        bind.execute(
            sa.text(
                "DELETE FROM user_module_client_scopes WHERE user_module_role_id IN "
                "(SELECT id FROM user_module_roles WHERE client_ref = :ref)"
            ),
            {"ref": demo_public_id},
        )
        bind.execute(
            sa.text("DELETE FROM user_module_roles WHERE client_ref = :ref"),
            {"ref": demo_public_id},
        )
        bind.execute(
            sa.text("DELETE FROM group_module_client_scopes WHERE client_ref = :ref"),
            {"ref": demo_public_id},
        )
        bind.execute(
            sa.text("DELETE FROM client_external_ids WHERE client_id = :cid"),
            {"cid": demo_client_id},
        )
        bind.execute(sa.text("DELETE FROM clients WHERE id = :cid"), {"cid": demo_client_id})


def downgrade() -> None:
    raise NotImplementedError(
        "Demo client identity (ABC/XYZ/Nova) is retired in favor of the "
        "real, DTC-verified client set. Recreating the demo rows here "
        "would not restore the user_module_roles/scope bindings this "
        "migration deleted (those are seed data, not migration data) — a "
        "genuine rollback means restoring a pre-migration database backup, "
        "not `alembic downgrade`. Same pattern as "
        "b8c9d0e1f2a3/c1d3e5f7a9b0 in talent-api."
    )
