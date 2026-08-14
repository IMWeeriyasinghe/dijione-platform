"""add employee_number to birthday_orders

Revision ID: a1b2c3d4e5f6
Revises: cb458018416c
Create Date: 2026-08-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'cb458018416c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Purely additive, nullable column — BambooHR's `employeeNumber` field
    (the real business Employee ID), distinct from the existing
    `employee_id` column which is BambooHR's internal record id and stays
    unchanged as the idempotency/join key. Nullable because BambooHR data
    proves employeeNumber can be blank for some employees. Existing rows
    are backfilled by the separate `scripts/backfill_employee_numbers.py`
    script (re-fetches each employee from BambooHR), not by this
    migration.
    """
    with op.batch_alter_table('birthday_orders', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('employee_number', sa.String(length=32), nullable=True)
        )
        batch_op.create_index(
            batch_op.f('ix_birthday_orders_employee_number'),
            ['employee_number'],
            unique=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('birthday_orders', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_birthday_orders_employee_number'))
        batch_op.drop_column('employee_number')
