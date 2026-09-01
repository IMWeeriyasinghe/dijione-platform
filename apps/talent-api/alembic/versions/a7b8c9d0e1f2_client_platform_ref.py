"""clients.platform_client_id — reference to platform-owned canonical identity

Architecture Completion Plan Wave A / A2 / §6.1. DijiTalentFlow's ``clients``
row becomes an *extension* of a platform-owned client organisation: it
carries the platform ``Client.public_id`` in ``platform_client_id`` and the
authorization resolver in ``app/api/deps.py`` maps a client-scope claim
(``client_public_id``) to the local integer id via this column.

Additive + a name-match backfill for the three demo organisations. The
local integer ``id`` and every TalentFlow foreign key referencing it are
unchanged.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-09-01 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# name -> platform Client.public_id (mirrors platform-api migration d4e5f6a7b8c9)
_BACKFILL = {
    "ABC Company": "cli-abc-company",
    "XYZ Company": "cli-xyz-company",
    "Nova Solutions": "cli-nova-solutions",
}


def upgrade() -> None:
    with op.batch_alter_table("clients", schema=None) as batch_op:
        batch_op.add_column(sa.Column("platform_client_id", sa.String(length=40), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_clients_platform_client_id"), ["platform_client_id"], unique=False
        )
    bind = op.get_bind()
    for name, public_id in _BACKFILL.items():
        bind.execute(
            sa.text("UPDATE clients SET platform_client_id = :p WHERE name = :n"),
            {"p": public_id, "n": name},
        )


def downgrade() -> None:
    with op.batch_alter_table("clients", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_clients_platform_client_id"))
        batch_op.drop_column("platform_client_id")
