"""drop external_mappings / integration_events (HubSpot moved to commercial-api)

Architecture Completion Plan Wave F. HubSpot ownership (stub client,
webhook, config) moved to the commercial-api skeleton — talent-api no
longer holds any HubSpot code. These two tables had no remaining writer in
talent-api (Lever's equivalents moved to recruitment-api in Wave C); their
event/mapping history, if ever needed, lives in the pre-Wave-C commit
history, not a live table.

Revision ID: c1d3e5f7a9b0
Revises: b8c9d0e1f2a3
Create Date: 2026-09-01 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c1d3e5f7a9b0"
down_revision: Union[str, Sequence[str], None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in ("external_mappings", "integration_events"):
        if sa.inspect(bind).has_table(table):
            op.drop_table(table)


def downgrade() -> None:
    raise NotImplementedError(
        "HubSpot ownership moved to commercial-api; recreate these tables "
        "there if a rollback is genuinely required."
    )
