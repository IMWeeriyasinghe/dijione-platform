"""add delivery address fields to birthday_orders

Revision ID: f3a91c7b2e04
Revises: c3d4e5f6a7b8
Create Date: 2026-08-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a91c7b2e04'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('birthday_orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('delivery_address_line1', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('delivery_address_line2', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('delivery_city', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('delivery_state_province', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('delivery_postal_code', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('delivery_country', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('delivery_address_source', sa.String(length=32), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('birthday_orders', schema=None) as batch_op:
        batch_op.drop_column('delivery_address_source')
        batch_op.drop_column('delivery_country')
        batch_op.drop_column('delivery_postal_code')
        batch_op.drop_column('delivery_state_province')
        batch_op.drop_column('delivery_city')
        batch_op.drop_column('delivery_address_line2')
        batch_op.drop_column('delivery_address_line1')
