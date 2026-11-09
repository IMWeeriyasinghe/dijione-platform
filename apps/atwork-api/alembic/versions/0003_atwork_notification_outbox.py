"""notification outbox

Revision ID: 0003_atwork_notifications
Revises: 0002_atwork_corrections
Create Date: 2026-11-09 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_atwork_notifications"
down_revision: str | Sequence[str] | None = "0002_atwork_corrections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("dedupe_key", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("link_url", sa.String(500), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("required_permissions", sa.JSON(), nullable=True),
        sa.Column("exclude_user_ids", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", _TS, nullable=False),
        sa.Column("created_at", _TS, nullable=False),
        sa.Column("sent_at", _TS, nullable=True),
        sa.CheckConstraint("status IN ('PENDING', 'SENT', 'FAILED')", name="ck_notification_outbox_status"),
        sa.UniqueConstraint("dedupe_key", name="uq_notification_outbox_dedupe_key"),
    )
    op.create_index("ix_notification_outbox_due", "notification_outbox", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_index("ix_notification_outbox_due", table_name="notification_outbox")
    op.drop_table("notification_outbox")
