"""BP role grants and employee scope tables

Revision ID: 0005_atwork_bp_role
Revises: 0004_atwork_reminders
Create Date: 2026-11-28 00:00:00.000000

Adds:
  atwork_bp_grants           — which employees hold the BP role
  atwork_bp_employee_scope   — which employees a BP can see in Management

BP source-of-truth — why manual assignment:
  The ``dijitalteam`` BambooHR tenant was surveyed live (2026-08-14) using
  GET /v1/meta/fields (400 total fields). No supervisor, manager, reports_to,
  or Business Partner relationship field exists in this tenant. BambooHR
  ``department`` for this business holds client engagement/bench assignment,
  not a hierarchical reporting relationship. There is therefore no authoritative
  automated source from which BP scope can be derived. Manual administrator
  assignment via these tables is the deliberate design, not a placeholder. If
  a future BambooHR custom field is added to represent the BP relationship,
  the workforce sync and these tables should be updated to prefer it; until
  then, the ``atwork_bp_employee_scope`` table is the sole authoritative source.
  Reference: docs/platform/bamboohr-live-discovery.md (address follow-up,
  field catalogue section).
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_atwork_bp_role"
down_revision = "0004_atwork_reminders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "atwork_bp_grants",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("platform_user_id", sa.Integer, nullable=False),
        sa.Column("granted_by", sa.Integer, nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_by", sa.Integer, nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, default=True),
    )
    op.create_index("ix_bp_grants_active", "atwork_bp_grants", ["platform_user_id", "is_active"])

    op.create_table(
        "atwork_bp_employee_scope",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("bp_platform_user_id", sa.Integer, nullable=False),
        sa.Column("employee_platform_user_id", sa.Integer, nullable=False),
        sa.Column("assigned_by", sa.Integer, nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("removed_by", sa.Integer, nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, default=True),
        sa.UniqueConstraint("bp_platform_user_id", "employee_platform_user_id", name="uq_bp_employee"),
    )
    op.create_index(
        "ix_bp_scope_bp_active",
        "atwork_bp_employee_scope",
        ["bp_platform_user_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_bp_scope_bp_active", table_name="atwork_bp_employee_scope")
    op.drop_table("atwork_bp_employee_scope")
    op.drop_index("ix_bp_grants_active", table_name="atwork_bp_grants")
    op.drop_table("atwork_bp_grants")
