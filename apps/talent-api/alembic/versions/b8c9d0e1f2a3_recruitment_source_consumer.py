"""DijiTalentFlow becomes a Recruitment Source consumer

Architecture Completion Plan Wave C. The Lever source read model moved to
recruitment-api (its own database). talent-api now:

- keeps a thin local ``recruitment_posting_refs`` projection (refreshed
  from recruitment-api's canonical DTO) so the fail-closed
  client-visibility join and the staff review screen keep working during a
  source outage;
- re-keys ``posting_client_mappings`` from a local ``postings.id`` FK to the
  stable ``(provider, posting_external_id)`` — trust/audit/DTC columns
  unchanged;
- drops the moved source tables: ``postings``, ``posting_applications``,
  ``recruitment_sync_runs``.

The ``posting_client_mappings`` re-key is done by an explicit table rebuild
(rename / create / copy / drop) rather than batch reflection, because the
old ``posting_id`` column carried a foreign key to ``postings``, which this
same migration removes.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-09-01 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1. local posting projection ------------------------------------------
    op.create_table(
        "recruitment_posting_refs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("dtc_status", sa.String(length=16), nullable=False),
        sa.Column("dtc_client_name", sa.String(length=255), nullable=True),
        sa.Column("dtc_raw_tag", sa.String(length=255), nullable=True),
        sa.Column("source_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("recruitment_posting_refs", schema=None) as b:
        b.create_index(
            b.f("ix_recruitment_posting_refs_external_id"), ["external_id"], unique=True
        )

    # 2. rebuild posting_client_mappings on the new key -------------------
    op.rename_table("posting_client_mappings", "posting_client_mappings_old")

    op.create_table(
        "posting_client_mappings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("posting_external_id", sa.String(length=128), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("verified_by_user_id", sa.Integer(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dtc_source_tag", sa.String(length=255), nullable=True),
        sa.Column("resolution_status", sa.String(length=32), nullable=False),
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "posting_external_id", name="uq_posting_client_mapping_ref"
        ),
    )

    has_postings = sa.inspect(bind).has_table("postings")
    ext_expr = (
        "(SELECT p.lever_posting_id FROM postings p WHERE p.id = o.posting_id)"
        if has_postings
        else "NULL"
    )
    bind.execute(
        sa.text(
            f"""
            INSERT INTO posting_client_mappings
                (id, provider, posting_external_id, client_id, status, source,
                 verified_by_user_id, verified_at, dtc_source_tag, resolution_status,
                 last_reconciled_at, created_at, updated_at)
            SELECT o.id, 'LEVER', {ext_expr}, o.client_id, o.status, o.source,
                   o.verified_by_user_id, o.verified_at, o.dtc_source_tag,
                   o.resolution_status, o.last_reconciled_at, o.created_at, o.updated_at
            FROM posting_client_mappings_old o
            """
        )
    )
    # a mapping whose posting id no longer resolves is not client-usable
    bind.execute(
        sa.text("DELETE FROM posting_client_mappings WHERE posting_external_id IS NULL")
    )
    # drop the old table (SQLite keeps the pre-rename index names attached to
    # it — must go before the new indexes are created to avoid a name clash)
    op.drop_table("posting_client_mappings_old")

    with op.batch_alter_table("posting_client_mappings", schema=None) as b:
        b.create_index(b.f("ix_posting_client_mappings_provider"), ["provider"], unique=False)
        b.create_index(
            b.f("ix_posting_client_mappings_posting_external_id"),
            ["posting_external_id"], unique=False,
        )
        b.create_index(
            b.f("ix_posting_client_mappings_client_id"), ["client_id"], unique=False
        )
        b.create_index(b.f("ix_posting_client_mappings_status"), ["status"], unique=False)

    # 3. drop the moved source tables -----------------------------------
    for table in ("posting_applications", "postings", "recruitment_sync_runs"):
        if sa.inspect(bind).has_table(table):
            op.drop_table(table)


def downgrade() -> None:
    raise NotImplementedError(
        "Wave C is a one-way ownership migration; recreate from recruitment-api "
        "if a rollback is genuinely required."
    )
