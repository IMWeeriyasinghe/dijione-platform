"""add transport_outcome to supplier_communications

Revision ID: 729cb1d84e60
Revises: a4c6e8f0b2d5
Create Date: 2026-09-14 00:00:00.000000

The truthful, transport-level mail outcome (mail_client_py.MailOutcome —
NOT_ATTEMPTED|DISABLED|BLOCKED|SIMULATED|SUBMITTED|FAILED), durable and
distinct from `status`, which continues to represent only Birthday's own
business/workflow state. Nullable — historical rows predating this column
are NULL, never backfilled.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '729cb1d84e60'
down_revision: Union[str, Sequence[str], None] = 'a4c6e8f0b2d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('supplier_communications', schema=None) as batch_op:
        batch_op.add_column(sa.Column('transport_outcome', sa.String(length=16), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('supplier_communications', schema=None) as batch_op:
        batch_op.drop_column('transport_outcome')
