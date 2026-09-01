"""magic_link_grants — DijiTalentFlow external client access grants

DijiTalentFlow external client (magic-link) access, Phase B / PR B1. Adds
the ``magic_link_grants`` table backing the new external-access architecture
(``get_talent_external_scope``, redeem endpoint — later PRs). This
migration is purely additive: it introduces one new table and touches no
existing schema.

Every fact an external session needs is resolved from this table on every
request, never trusted from the session JWT (see
``app/models/magic_link_grant.py``). ``token_hash`` is the SHA-256 digest of
the raw, one-time-displayed token — the raw token itself is never a column
here. ``client_id`` FKs into this database's own ``clients`` table (the
TalentFlow extension of the platform-owned canonical client, not a new
identity concept).

Revision ID: e7f8a9b0c1d2
Revises: d2f4a6b8c0e1
Create Date: 2026-09-02 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, Sequence[str], None] = "d2f4a6b8c0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "magic_link_grants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column(
            "scope_type", sa.String(length=32), nullable=False, server_default="CLIENT_WORKSPACE"
        ),
        sa.Column("contact_email", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("contact_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_prefix", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("issued_by_user_id", sa.Integer(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_magic_link_grants_public_id", "magic_link_grants", ["public_id"], unique=True
    )
    op.create_index("ix_magic_link_grants_client_id", "magic_link_grants", ["client_id"])
    op.create_index(
        "ix_magic_link_grants_token_hash", "magic_link_grants", ["token_hash"], unique=True
    )
    op.create_index("ix_magic_link_grants_expires_at", "magic_link_grants", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_magic_link_grants_expires_at", table_name="magic_link_grants")
    op.drop_index("ix_magic_link_grants_token_hash", table_name="magic_link_grants")
    op.drop_index("ix_magic_link_grants_client_id", table_name="magic_link_grants")
    op.drop_index("ix_magic_link_grants_public_id", table_name="magic_link_grants")
    op.drop_table("magic_link_grants")
