"""employees.mobile_phone / home_phone — team-member delivery contacts (additive).

Revision ID: 0005_people_contact_numbers
Revises: 0004_people_workforce_photo
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_people_contact_numbers"
down_revision: str | Sequence[str] | None = "0004_people_workforce_photo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("mobile_phone", sa.String(length=64), nullable=True))
    op.add_column("employees", sa.Column("home_phone", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("employees", "home_phone")
    op.drop_column("employees", "mobile_phone")
