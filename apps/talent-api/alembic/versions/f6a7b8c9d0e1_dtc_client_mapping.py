"""posting_client_mappings — DTC-tag reconciliation provenance/diagnostics.

Additive only: three nullable/defaulted columns so the governed
"DTC - <Client Name>" Lever posting tag can drive client resolution into the
existing trust record. The fail-closed query (status==VERIFIED AND
client_id) is unchanged. No data rewrite — the next sync's reconciler
stamps every row.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-31 11:55:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("posting_client_mappings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("dtc_source_tag", sa.String(length=255), nullable=True))
        batch_op.add_column(
            sa.Column(
                "resolution_status",
                sa.String(length=32),
                nullable=False,
                server_default="NO_DTC_TAG",
            )
        )
        batch_op.add_column(
            sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("posting_client_mappings", schema=None) as batch_op:
        batch_op.drop_column("last_reconciled_at")
        batch_op.drop_column("resolution_status")
        batch_op.drop_column("dtc_source_tag")
