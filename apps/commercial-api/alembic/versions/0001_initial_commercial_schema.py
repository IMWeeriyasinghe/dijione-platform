"""initial Commercial / CRM schema (skeleton)

Architecture Completion Plan Wave F. Only integration_events — the HubSpot
webhook idempotency log, moved here from talent-api. No canonical
company/contact read model yet (deferred until HubSpot access lands).

Revision ID: 0001_commercial_initial
Revises:
Create Date: 2026-09-01 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0001_commercial_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "integration_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_status", sa.String(length=32), nullable=False),
        sa.Column("payload_reference", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "external_event_id", name="uq_provider_event"),
    )
    with op.batch_alter_table("integration_events", schema=None) as b:
        b.create_index(b.f("ix_integration_events_provider"), ["provider"], unique=False)


def downgrade() -> None:
    op.drop_table("integration_events")
