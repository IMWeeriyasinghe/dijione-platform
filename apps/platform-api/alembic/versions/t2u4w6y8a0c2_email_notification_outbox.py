"""Email notification outbox, access snapshots, event settings, test recipients

Schema only — four new platform-owned tables, no change to any existing table or row:

* ``email_outbox`` — transactional outbox + delivery history for platform emails;
* ``user_access_snapshots`` — the effective access each person was last notified about;
* ``notification_event_settings`` — per-event on/off switches (absent row = enabled);
* ``email_test_recipients`` — the DEV/UAT recipient allowlist.

Additive and reversible: downgrade drops the four tables (losing only email history and
settings; no access data). No user receives an email because of this migration: existing
people get a silent baseline snapshot (``python -m app.services.access_notifications backfill``,
also run by the dispatcher on start) before any change is compared with it.

Revision ID: t2u4w6y8a0c2
Revises: s1t3v5x7z9b1
Create Date: 2026-11-20 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "t2u4w6y8a0c2"
down_revision: str | Sequence[str] | None = "s1t3v5x7z9b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _existing() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    # Idempotent (repository convention): a re-run after a stamp skips what already exists.
    existing = _existing()
    if "email_outbox" not in existing:
        _create_outbox()
    if "user_access_snapshots" not in existing:
        _create_snapshots()
    if "notification_event_settings" not in existing:
        _create_event_settings()
    if "email_test_recipients" not in existing:
        _create_test_recipients()


def _create_outbox() -> None:
    op.create_table(
        "email_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("correlation_id", sa.String(36), nullable=False),
        sa.Column("application_key", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("recipient_email", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("template_key", sa.String(64), nullable=False),
        sa.Column("template_data", sa.JSON(), nullable=False),
        sa.Column("from_snapshot", sa.JSON(), nullable=True),
        sa.Column("dedupe_key", sa.String(200), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transport_outcome", sa.String(16), nullable=True),
        sa.Column("graph_request_id", sa.String(128), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("superseded_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("dedupe_key", name="uq_email_outbox_dedupe_key"),
        sa.UniqueConstraint("correlation_id", name="uq_email_outbox_correlation_id"),
    )
    for column in ("application_key", "event_type", "recipient_user_id", "recipient_email", "status", "not_before"):
        op.create_index(f"ix_email_outbox_{column}", "email_outbox", [column])


def _create_snapshots() -> None:
    op.create_table(
        "user_access_snapshots",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("welcomed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def _create_event_settings() -> None:
    op.create_table(
        "notification_event_settings",
        sa.Column("event_type", sa.String(64), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def _create_test_recipients() -> None:
    op.create_table(
        "email_test_recipients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("address", sa.String(255), nullable=False, unique=True),
        sa.Column("label", sa.String(255), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    existing = _existing()
    for table in ("email_test_recipients", "notification_event_settings", "user_access_snapshots"):
        if table in existing:
            op.drop_table(table)
    if "email_outbox" in existing:
        for column in ("application_key", "event_type", "recipient_user_id", "recipient_email", "status", "not_before"):
            op.drop_index(f"ix_email_outbox_{column}", table_name="email_outbox")
        op.drop_table("email_outbox")
