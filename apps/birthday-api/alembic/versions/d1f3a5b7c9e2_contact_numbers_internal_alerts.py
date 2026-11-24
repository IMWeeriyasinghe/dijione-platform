"""team-member contact numbers on orders; P&C supplier-activity email alerts

Revision ID: d1f3a5b7c9e2
Revises: b5e7c9d1f3a2
Create Date: 2026-11-24

Additive and backward-safe: all new columns are nullable and the new table
is only read by this release, so older images keep working against it.
Historical orders simply have no contact numbers.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d1f3a5b7c9e2"
down_revision: str | Sequence[str] | None = "b5e7c9d1f3a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("birthday_orders", schema=None) as batch_op:
        batch_op.add_column(sa.Column("employee_mobile_phone", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("employee_home_phone", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("delivery_contact_phone", sa.String(length=64), nullable=True))

    with op.batch_alter_table("birthday_detection_configs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("ops_alert_recipients", sa.Text(), nullable=True))

    op.create_table(
        "birthday_internal_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("birthday_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("source_key", sa.String(length=64), nullable=False),
        sa.Column("recipient", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PENDING"),
        sa.Column("transport_outcome", sa.String(length=16), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source_key", "recipient", name="uq_internal_alert_source_recipient"),
    )
    op.create_index("ix_birthday_internal_alerts_order_id", "birthday_internal_alerts", ["order_id"])
    op.create_index("ix_birthday_internal_alerts_source_key", "birthday_internal_alerts", ["source_key"])


def downgrade() -> None:
    op.drop_index("ix_birthday_internal_alerts_source_key", table_name="birthday_internal_alerts")
    op.drop_index("ix_birthday_internal_alerts_order_id", table_name="birthday_internal_alerts")
    op.drop_table("birthday_internal_alerts")
    with op.batch_alter_table("birthday_detection_configs", schema=None) as batch_op:
        batch_op.drop_column("ops_alert_recipients")
    with op.batch_alter_table("birthday_orders", schema=None) as batch_op:
        batch_op.drop_column("delivery_contact_phone")
        batch_op.drop_column("employee_home_phone")
        batch_op.drop_column("employee_mobile_phone")
