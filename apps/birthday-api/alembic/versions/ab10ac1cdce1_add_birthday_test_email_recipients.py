"""add birthday_test_email_recipients

Revision ID: ab10ac1cdce1
Revises: 729cb1d84e60
Create Date: 2026-09-15 00:00:00.000000

DijiBirthday-owned, non-production outbound-recipient safety allowlist
(app/models/birthday_test_email_recipient.py). No environment column by
design — DEV/UAT/PROD already use separate databases, so this table is
already environment-isolated by which database it lives in. Pure schema
change; no data is seeded here (see
apps/birthday-api/scripts/seed_test_email_recipients.py for the
idempotent, DEV-only bootstrap of the two initial approved test
recipients).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'ab10ac1cdce1'
down_revision: str | Sequence[str] | None = '729cb1d84e60'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'birthday_test_email_recipients',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email_address', sa.String(length=255), nullable=False),
        sa.Column('normalized_email_address', sa.String(length=255), nullable=False),
        sa.Column('display_label', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('recipient_type', sa.String(length=32), nullable=False, server_default='INTERNAL_TESTER'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('birthday_test_email_recipients', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_birthday_test_email_recipients_normalized_email_address'),
            ['normalized_email_address'], unique=True,
        )
    # server_default was only needed to backfill this table's own creation
    # (it starts empty, so there's nothing to backfill in practice) — drop
    # it so the ORM model's own defaults remain the single source of truth
    # going forward, matching this repo's established migration convention
    # (see f8b3d1a4c206_add_is_default_to_suppliers.py).
    with op.batch_alter_table('birthday_test_email_recipients', schema=None) as batch_op:
        batch_op.alter_column('display_label', server_default=None)
        batch_op.alter_column('recipient_type', server_default=None)
        batch_op.alter_column('is_active', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('birthday_test_email_recipients', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_birthday_test_email_recipients_normalized_email_address'))
    op.drop_table('birthday_test_email_recipients')
