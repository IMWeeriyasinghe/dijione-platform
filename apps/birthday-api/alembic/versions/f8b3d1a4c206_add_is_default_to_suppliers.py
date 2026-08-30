"""add is_default (island-wide / catch-all) flag to suppliers

Revision ID: f8b3d1a4c206
Revises: e7f2a0b1c9d3
Create Date: 2026-08-29 12:00:00.000000

When birthday detection cannot resolve a supplier from the team member's
office location, the single ACTIVE supplier flagged is_default is used
instead — the common case for a business with one island-wide supplier.
At most one supplier holds the flag (enforced in the create/update routes).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8b3d1a4c206'
down_revision: Union[str, Sequence[str], None] = 'e7f2a0b1c9d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('suppliers', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.false())
        )
    # Drop the server_default now that existing rows are populated — the ORM
    # model default (False) is the source of truth going forward.
    with op.batch_alter_table('suppliers', schema=None) as batch_op:
        batch_op.alter_column('is_default', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('suppliers', schema=None) as batch_op:
        batch_op.drop_column('is_default')
