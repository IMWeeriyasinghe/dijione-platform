"""verified identity mapping layer (ZKBioTime ID -> BambooHR identity)

Adds three DijiOne-owned tables to onsite_<env>; no existing table or row is
touched (attendance_events stays a verbatim mirror). Mapping data is
per-environment operational data and is never promoted between environments.

The downgrade exists for CI (fresh SQLite / Postgres upgrade-downgrade-upgrade)
only. It must never be run against DEV/UAT/PROD: recovery is forward-only.

Revision ID: 0002_onsite_identity
Revises: 0001_onsite_initial
Create Date: 2026-11-14 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_onsite_identity"
down_revision: Union[str, Sequence[str], None] = "0001_onsite_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OPEN = "status = 'VERIFIED' AND valid_to IS NULL"


def upgrade() -> None:
    op.create_table(
        "onsite_identity_mappings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("site_id", sa.String(length=64), nullable=False),
        sa.Column("zk_emp_code", sa.String(length=20), nullable=False),
        sa.Column("bamboohr_id", sa.String(length=64), nullable=False),
        sa.Column("employee_number_snapshot", sa.String(length=32), nullable=True),
        sa.Column("display_name_snapshot", sa.String(length=200), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("verified_by_user_id", sa.Integer(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_reason", sa.Text(), nullable=True),
        sa.Column("superseded_by_id", sa.Integer(), nullable=True),
        sa.Column("superseded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_reason", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("import_batch_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="ck_idmap_period"),
        sa.CheckConstraint("status IN ('VERIFIED','SUPERSEDED')", name="ck_idmap_status"),
        sa.CheckConstraint("source IN ('MANUAL','IMPORT')", name="ck_idmap_source"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_idmap_site_code_from", "onsite_identity_mappings", ["site_id", "zk_emp_code", "valid_from"])
    op.create_index("ix_idmap_bamboohr", "onsite_identity_mappings", ["bamboohr_id"])
    op.create_index("ux_idmap_open_verified", "onsite_identity_mappings", ["site_id", "zk_emp_code"], unique=True,
                    sqlite_where=sa.text(_OPEN), postgresql_where=sa.text(_OPEN))

    op.create_table(
        "onsite_identity_rejections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("site_id", sa.String(length=64), nullable=False),
        sa.Column("zk_emp_code", sa.String(length=20), nullable=False),
        sa.Column("bamboohr_id", sa.String(length=64), nullable=False),
        sa.Column("applies_from", sa.Date(), nullable=True),
        sa.Column("applies_to", sa.Date(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("rejected_by_user_id", sa.Integer(), nullable=False),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withdrawn_by_user_id", sa.Integer(), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("applies_to IS NULL OR applies_from IS NULL OR applies_to >= applies_from",
                           name="ck_idrej_period"),
        sa.CheckConstraint("status IN ('ACTIVE','WITHDRAWN')", name="ck_idrej_status"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_idrej_pair", "onsite_identity_rejections", ["site_id", "zk_emp_code", "bamboohr_id"])

    op.create_table(
        "onsite_identity_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_type", sa.String(length=16), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_json", sa.Text(), nullable=True),
        sa.Column("new_json", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_idev_entity", "onsite_identity_events", ["entity_type", "entity_id"])
    op.create_index("ix_idev_at", "onsite_identity_events", ["at"])


def downgrade() -> None:
    # CI only (see module docstring). Never run against a live environment.
    op.drop_index("ix_idev_at", table_name="onsite_identity_events")
    op.drop_index("ix_idev_entity", table_name="onsite_identity_events")
    op.drop_table("onsite_identity_events")
    op.drop_index("ix_idrej_pair", table_name="onsite_identity_rejections")
    op.drop_table("onsite_identity_rejections")
    op.drop_index("ux_idmap_open_verified", table_name="onsite_identity_mappings")
    op.drop_index("ix_idmap_bamboohr", table_name="onsite_identity_mappings")
    op.drop_index("ix_idmap_site_code_from", table_name="onsite_identity_mappings")
    op.drop_table("onsite_identity_mappings")
