"""DIJI Birthday does not read client scope

l2m3n4o5p6q7 introduced ``application_modules.supports_client_scope`` defaulting to true for every
module then registered, and set it false only for Diji On-site. DIJI Birthday's authorization has never
read client scope (birthday-api uses only the module role and permissions), so true was a default,
not a decision. It made Central Admin and the delegated Access page ask for a client scope that
birthday-api ignores.

Registry metadata only. No assignment, client-scope row, group or user is touched, and no session's
claims change (claims are computed from the assignment rows, not from this flag), so no access_version
bump is needed. Idempotent. Downgrade restores the previous value.

Revision ID: r9t1v3x5z7b9
Revises: q8s0u2w4y6a8
Create Date: 2026-11-18 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "r9t1v3x5z7b9"
down_revision: str | Sequence[str] | None = "q8s0u2w4y6a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE application_modules SET supports_client_scope = false WHERE key = 'birthday'")


def downgrade() -> None:
    op.execute("UPDATE application_modules SET supports_client_scope = true WHERE key = 'birthday'")
