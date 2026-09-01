"""canonical client/organisation identity (platform-owned master data)

Architecture Completion Plan Wave A / §6.1. platform-api becomes the
permanent owner of canonical Client / Organisation identity:

- new ``clients`` master table (``public_id`` is the stable, non-sequential
  identifier every other service references) + ``client_external_ids``
  crosswalk;
- seeds the three demo organisations (ABC / XYZ / Nova) with fixed
  ``public_id`` slugs and a ``talent-api`` crosswalk to their legacy
  integer ids (1 / 2 / 3);
- adds ``client_ref`` to ``user_module_client_scopes``,
  ``group_module_client_scopes`` and ``user_module_roles`` and backfills it
  from the legacy ``client_id`` via that crosswalk.

The legacy ``client_id`` integers are left in place for one migration
cycle and dropped in a follow-up once nothing reads them.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-01 00:00:00.000000
"""

from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ABC=1 / XYZ=2 / Nova=3 — the seed-order convention this migration retires.
_SEED_CLIENTS = [
    ("cli-abc-company", "ABC Company", "1"),
    ("cli-xyz-company", "XYZ Company", "2"),
    ("cli-nova-solutions", "Nova Solutions", "3"),
]


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    with op.batch_alter_table("clients", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_clients_public_id"), ["public_id"], unique=True)

    op.create_table(
        "client_external_ids",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "external_id", name="uq_client_external_id"),
    )
    with op.batch_alter_table("client_external_ids", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_client_external_ids_client_id"), ["client_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_client_external_ids_provider"), ["provider"], unique=False
        )

    for table in ("user_module_client_scopes", "group_module_client_scopes", "user_module_roles"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column("client_ref", sa.String(length=40), nullable=True))
            batch_op.create_index(batch_op.f(f"ix_{table}_client_ref"), ["client_ref"], unique=False)

    # --- seed canonical clients + legacy crosswalk ------------------------
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
    xref_t = sa.table(
        "client_external_ids",
        sa.column("client_id", sa.Integer),
        sa.column("provider", sa.String),
        sa.column("external_id", sa.String),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    bind = op.get_bind()
    for idx, (public_id, name, legacy_id) in enumerate(_SEED_CLIENTS, start=1):
        existing = bind.execute(
            sa.text("SELECT id FROM clients WHERE public_id = :p"), {"p": public_id}
        ).first()
        if existing is None:
            op.bulk_insert(
                clients_t,
                [{
                    "public_id": public_id, "name": name, "status": "ACTIVE",
                    "created_at": now, "updated_at": now,
                }],
            )
        row = bind.execute(
            sa.text("SELECT id FROM clients WHERE public_id = :p"), {"p": public_id}
        ).first()
        client_pk = row[0]
        has_xref = bind.execute(
            sa.text(
                "SELECT 1 FROM client_external_ids WHERE provider = 'talent-api' "
                "AND external_id = :e"
            ),
            {"e": legacy_id},
        ).first()
        if has_xref is None:
            op.bulk_insert(
                xref_t,
                [{
                    "client_id": client_pk, "provider": "talent-api", "external_id": legacy_id,
                    "created_at": now, "updated_at": now,
                }],
            )

    # --- backfill client_ref from the legacy client_id integer -----------
    for table in ("user_module_client_scopes", "group_module_client_scopes", "user_module_roles"):
        bind.execute(
            sa.text(
                f"UPDATE {table} SET client_ref = ("
                "  SELECT c.public_id FROM clients c "
                "  JOIN client_external_ids x ON x.client_id = c.id "
                "  WHERE x.provider = 'talent-api' "
                f"    AND x.external_id = CAST({table}.client_id AS TEXT)"
                f") WHERE {table}.client_id IS NOT NULL"
            )
        )


def downgrade() -> None:
    for table in ("user_module_roles", "group_module_client_scopes", "user_module_client_scopes"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_index(batch_op.f(f"ix_{table}_client_ref"))
            batch_op.drop_column("client_ref")
    with op.batch_alter_table("client_external_ids", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_client_external_ids_provider"))
        batch_op.drop_index(batch_op.f("ix_client_external_ids_client_id"))
    op.drop_table("client_external_ids")
    with op.batch_alter_table("clients", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_clients_public_id"))
    op.drop_table("clients")
