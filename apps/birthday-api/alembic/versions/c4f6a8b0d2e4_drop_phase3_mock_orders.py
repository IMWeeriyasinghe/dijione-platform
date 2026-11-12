"""drop the Phase-3 DEV mock birthday orders

Hosted DEV ran the birthday scan against 10 mock employees (bhr-10## ids)
before the real People/BambooHR integration was activated, creating 8
REQUIRES_ATTENTION orders. Those employees are being removed from
people_dev (people-api 0002_people_drop_mock); these orders are the
matching obsolete DEV bootstrap data. Deletes ONLY orders whose
employee_id starts with the mock prefix 'bhr-10' AND that are still in the
initial REQUIRES_ATTENTION state (never dispatched), and only when the
count is small (<= 25). order_events / order_issues cascade.

No-op on SQLite.

Revision ID: c4f6a8b0d2e4_drop_mock_orders
Revises: b2d4f6a8c1e3
Create Date: 2026-09-08 00:00:00.000000
"""

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "c4f6a8b0d2e4_drop_mock_orders"
down_revision: str | Sequence[str] | None = "b2d4f6a8c1e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PRED = "employee_id LIKE 'bhr-10%' AND status = 'REQUIRES_ATTENTION'"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    n = bind.execute(text(f"SELECT count(*) FROM birthday_orders WHERE {_PRED}")).scalar_one()
    if n and n <= 25:
        bind.execute(text(f"DELETE FROM birthday_orders WHERE {_PRED}"))


def downgrade() -> None:
    pass
