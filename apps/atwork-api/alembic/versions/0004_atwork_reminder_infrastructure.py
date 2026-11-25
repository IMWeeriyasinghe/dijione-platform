"""reminder watermark and email tracking tables

Revision ID: 0004_atwork_reminders
Revises: 0003_atwork_notifications
Create Date: 2026-11-25 00:00:00.000000

Adds:
  atwork_reminder_watermark  — single-row deploy timestamp; sessions checked
                               in before this date are excluded from staged
                               reminders (rollout suppression).
  atwork_reminder_email_sent — per-(session, stage) email send tracking with
                               transaction-safe claiming.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_atwork_reminders"
down_revision: str | None = "0003_atwork_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    # Watermark: populated once at migration time so pre-existing open sessions
    # are never sent staged reminders after this feature is deployed.
    op.create_table(
        "atwork_reminder_watermark",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("watermark_at", _TS, nullable=False),
        sa.CheckConstraint("id = 1", name="ck_atwork_reminder_watermark_single"),
        sa.PrimaryKeyConstraint("id", name="pk_atwork_reminder_watermark"),
    )
    # Seed: any session checked in before this migration runs is excluded from
    # staged reminders — the watermark prevents replaying reminders on deploy.
    op.execute(
        sa.text(
            "INSERT INTO atwork_reminder_watermark (id, watermark_at) "
            "VALUES (1, CURRENT_TIMESTAMP)"
        )
    )

    # Email tracking table.
    op.create_table(
        "atwork_reminder_email_sent",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("stage", sa.Integer(), nullable=False),
        sa.Column("recipient_email", sa.String(255), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", _TS, nullable=False),
        sa.Column("created_at", _TS, nullable=False),
        sa.Column("sent_at", _TS, nullable=True),
        sa.CheckConstraint("status IN ('PENDING','SENT','FAILED')", name="ck_reminder_email_status"),
        sa.CheckConstraint("stage IN (1,2,3)", name="ck_reminder_email_stage"),
        sa.UniqueConstraint("session_id", "stage", name="uq_reminder_email_session_stage"),
        sa.PrimaryKeyConstraint("id", name="pk_atwork_reminder_email_sent"),
    )
    op.create_index("ix_reminder_email_pending", "atwork_reminder_email_sent", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_index("ix_reminder_email_pending", table_name="atwork_reminder_email_sent")
    op.drop_table("atwork_reminder_email_sent")
    op.drop_table("atwork_reminder_watermark")
