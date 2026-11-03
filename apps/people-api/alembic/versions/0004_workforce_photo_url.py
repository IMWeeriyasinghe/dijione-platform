"""workforce_directory.photo_url — BambooHR profile photo link (additive).

Revision ID: 0004_people_workforce_photo
Revises: 0003_people_workforce
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_people_workforce_photo"
down_revision: str | Sequence[str] | None = "0003_people_workforce"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("workforce_directory", sa.Column("photo_url", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column("workforce_directory", "photo_url")
