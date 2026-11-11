"""merge the audit event_id branch with module baseline roles

No schema change. DEV applied a7e1d0c4b9f2 directly on o5p6q7r8s9t0; the
release line added p6q7r8s9t0u1 on the same parent. This joins them so each
database runs each migration once. See docs/platform/audit-migration-integration.md.

Revision ID: c9d2e4f6a8b1
Revises: p6q7r8s9t0u1, a7e1d0c4b9f2
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

revision: str = "c9d2e4f6a8b1"
down_revision: str | Sequence[str] | None = ("p6q7r8s9t0u1", "a7e1d0c4b9f2")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
