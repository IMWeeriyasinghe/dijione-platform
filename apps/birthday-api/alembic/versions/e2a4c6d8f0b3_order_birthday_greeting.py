"""birthday_orders.birthday_greeting — editable birthday message for the supplier

Revision ID: e2a4c6d8f0b3
Revises: d1f3a5b7c9e2
Create Date: 2026-11-25

Additive and backward-safe: one nullable column. Existing orders keep NULL
(a legacy order without a greeting); new orders get the default greeting at
creation, and a legacy order is initialised when it is released.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e2a4c6d8f0b3"
down_revision: str | Sequence[str] | None = "d1f3a5b7c9e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("birthday_orders", schema=None) as batch_op:
        batch_op.add_column(sa.Column("birthday_greeting", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("birthday_orders", schema=None) as batch_op:
        batch_op.drop_column("birthday_greeting")
