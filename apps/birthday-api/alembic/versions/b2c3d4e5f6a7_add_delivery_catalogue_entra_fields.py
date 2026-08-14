"""add delivery_date/catalogue_item_id to birthday_orders, entra_object_id to supplier_users

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-14 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema. Purely additive/nullable columns."""
    with op.batch_alter_table('birthday_orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('delivery_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('catalogue_item_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_birthday_orders_catalogue_item_id',
            'supplier_catalogue_items', ['catalogue_item_id'], ['id'],
        )

    with op.batch_alter_table('supplier_users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('entra_object_id', sa.String(length=64), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_supplier_users_entra_object_id'), ['entra_object_id'], unique=True,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('supplier_users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_supplier_users_entra_object_id'))
        batch_op.drop_column('entra_object_id')

    with op.batch_alter_table('birthday_orders', schema=None) as batch_op:
        batch_op.drop_constraint('fk_birthday_orders_catalogue_item_id', type_='foreignkey')
        batch_op.drop_column('catalogue_item_id')
        batch_op.drop_column('delivery_date')
