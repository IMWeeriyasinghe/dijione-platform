"""scan_runs.status — DEFERRED_SOURCE_UNAVAILABLE outcome

Architecture Completion Plan Wave E. When people-api (the People /
Workforce source domain) is unreachable, run_daily_scan now defers safely
instead of raising mid-run: it touches no BirthdayOrder, records
DEFERRED_SOURCE_UNAVAILABLE, and the next scan naturally catches up. This
additive column lets scan-run history show that outcome distinctly from a
normal COMPLETED run. Existing rows default to COMPLETED (they all
completed normally under the pre-Wave-E synchronous BambooHR call).

Revision ID: b2d4f6a8c1e3
Revises: a1c9e3f5b7d2
Create Date: 2026-09-01 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b2d4f6a8c1e3"
down_revision: Union[str, Sequence[str], None] = "a1c9e3f5b7d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("scan_runs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("status", sa.String(length=32), nullable=False, server_default="COMPLETED")
        )


def downgrade() -> None:
    with op.batch_alter_table("scan_runs", schema=None) as batch_op:
        batch_op.drop_column("status")
