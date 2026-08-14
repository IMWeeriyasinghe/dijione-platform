"""add role to supplier_users, default status to ACTIVE

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-14 00:00:02.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema. Additive column; existing rows backfilled to
    SUPPLIER_USER via server_default, then the default dropped so the
    ORM-level Python default governs new rows (matches every other column
    on this model)."""
    with op.batch_alter_table('supplier_users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('role', sa.String(length=32), nullable=False, server_default='SUPPLIER_USER')
        )
    with op.batch_alter_table('supplier_users', schema=None) as batch_op:
        batch_op.alter_column('role', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('supplier_users', schema=None) as batch_op:
        batch_op.drop_column('role')
