"""add approval provenance (approved_at, approved_by) to birthday_orders

Revision ID: e7f2a0b1c9d3
Revises: f3a91c7b2e04
Create Date: 2026-08-29 00:00:00.000000

Phase-Next §19 QA/QC pass: approval must capture the approver and the
approval time as a first-class fact on the order, not only as an
OrderEvent. order_email_service._send() now gates on approved_at rather
than the current status, closing the gap where a detection-time
REQUIRES_ATTENTION order that was never approved could still be sent to a
supplier.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7f2a0b1c9d3'
down_revision: Union[str, Sequence[str], None] = 'f3a91c7b2e04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('birthday_orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('approved_by', sa.Integer(), nullable=True))

    # Backfill: existing orders that are already APPROVED or further along
    # the fulfilment lifecycle were, by the pre-approval-workflow rules,
    # implicitly approved — stamp approved_at so a resend does not suddenly
    # fail the new gate. detection-time REQUIRES_ATTENTION / DRAFT rows are
    # deliberately left NULL (they must go through approve()).
    op.execute(
        """
        UPDATE birthday_orders
        SET approved_at = COALESCE(approved_at, updated_at)
        WHERE status IN (
            'APPROVED', 'SENT_TO_SUPPLIER', 'SUPPLIER_REVIEW', 'CHANGE_REQUESTED',
            'CONFIRMED', 'PREPARING', 'OUT_FOR_DELIVERY', 'DELIVERED', 'COMPLETED'
        )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('birthday_orders', schema=None) as batch_op:
        batch_op.drop_column('approved_by')
        batch_op.drop_column('approved_at')
