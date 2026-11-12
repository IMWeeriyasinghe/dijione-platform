"""drop the Phase-3 DEV mock employees

Hosted DEV was seeded with 10 mock employees (bhr-10## ids, @example.com
work emails) before the real BambooHR integration was activated. The live
People sync now holds 336 real dijitalteam employees; the mock rows are
obsolete DEV bootstrap data and would otherwise pollute birthday detection
and the People directory. This deletes ONLY rows whose work_email is an
@example.com address — no real Dijital Team employee has one — and only
when the count is small (<= 25), so it can never touch a real dataset.

No-op on SQLite (local dev / CI never carries these rows).

Revision ID: 0002_people_drop_mock
Revises: 0001_people_initial
Create Date: 2026-09-08 00:00:00.000000
"""

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "0002_people_drop_mock"
down_revision: str | Sequence[str] | None = "0001_people_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    n = bind.execute(
        text("SELECT count(*) FROM employees WHERE work_email ILIKE '%@example.com'")
    ).scalar_one()
    if n and n <= 25:
        bind.execute(text("DELETE FROM employees WHERE work_email ILIKE '%@example.com'"))


def downgrade() -> None:
    # Mock seed data is not restorable and must not come back.
    pass
