"""initial Recruitment Source schema

Architecture Completion Plan Wave B. The Lever source read model, extracted
from talent-api into its own domain database (recruitment_dev). Tables:
postings, recruitment_candidates, recruitment_candidacies, external_mappings,
integration_events, recruitment_sync_runs.

Revision ID: 0001_recruitment_initial
Revises:
Create Date: 2026-09-01 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0001_recruitment_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "postings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lever_posting_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("team", sa.String(length=255), nullable=False),
        sa.Column("department", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=False),
        sa.Column("owner_user_id", sa.String(length=128), nullable=False),
        sa.Column("hiring_manager_user_id", sa.String(length=128), nullable=False),
        sa.Column("confidentiality", sa.String(length=32), nullable=False),
        sa.Column("tags", sa.Text(), nullable=False),
        sa.Column("lever_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lever_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("postings", schema=None) as b:
        b.create_index(b.f("ix_postings_lever_posting_id"), ["lever_posting_id"], unique=True)

    op.create_table(
        "recruitment_candidates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lever_contact_id", sa.String(length=128), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("headline", sa.String(length=255), nullable=False),
        sa.Column("tags", sa.Text(), nullable=False),
        sa.Column("sources", sa.Text(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("recruitment_candidates", schema=None) as b:
        b.create_index(
            b.f("ix_recruitment_candidates_lever_contact_id"), ["lever_contact_id"], unique=True
        )
        b.create_index(b.f("ix_recruitment_candidates_email"), ["email"], unique=False)

    op.create_table(
        "recruitment_candidacies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recruitment_candidate_id", sa.Integer(), nullable=False),
        sa.Column("posting_id", sa.Integer(), nullable=False),
        sa.Column("lever_opportunity_id", sa.String(length=128), nullable=False),
        sa.Column("current_stage", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("lever_archive_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["recruitment_candidate_id"], ["recruitment_candidates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["posting_id"], ["postings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("recruitment_candidacies", schema=None) as b:
        b.create_index(
            b.f("ix_recruitment_candidacies_recruitment_candidate_id"),
            ["recruitment_candidate_id"], unique=False,
        )
        b.create_index(
            b.f("ix_recruitment_candidacies_posting_id"), ["posting_id"], unique=False
        )
        b.create_index(
            b.f("ix_recruitment_candidacies_lever_opportunity_id"),
            ["lever_opportunity_id"], unique=True,
        )

    op.create_table(
        "external_mappings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_object_type", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("internal_object_type", sa.String(length=64), nullable=False),
        sa.Column("internal_id", sa.Integer(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_status", sa.String(length=16), nullable=False),
        sa.Column("sync_error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "external_object_type", "external_id", name="uq_external_object"
        ),
    )
    with op.batch_alter_table("external_mappings", schema=None) as b:
        b.create_index(b.f("ix_external_mappings_provider"), ["provider"], unique=False)
        b.create_index(b.f("ix_external_mappings_external_id"), ["external_id"], unique=False)
        b.create_index(b.f("ix_external_mappings_internal_id"), ["internal_id"], unique=False)

    op.create_table(
        "integration_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_status", sa.String(length=32), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("payload_reference", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "external_event_id", name="uq_provider_event"),
    )
    with op.batch_alter_table("integration_events", schema=None) as b:
        b.create_index(b.f("ix_integration_events_provider"), ["provider"], unique=False)

    op.create_table(
        "recruitment_sync_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("trigger_type", sa.String(length=16), nullable=False),
        sa.Column("requested_by_application", sa.String(length=64), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("records_read", sa.Integer(), nullable=False),
        sa.Column("records_created", sa.Integer(), nullable=False),
        sa.Column("records_updated", sa.Integer(), nullable=False),
        sa.Column("records_unchanged", sa.Integer(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("recruitment_sync_runs", schema=None) as b:
        b.create_index(b.f("ix_recruitment_sync_runs_run_id"), ["run_id"], unique=True)
        b.create_index(b.f("ix_recruitment_sync_runs_status"), ["status"], unique=False)


def downgrade() -> None:
    op.drop_table("recruitment_sync_runs")
    op.drop_table("integration_events")
    op.drop_table("external_mappings")
    op.drop_table("recruitment_candidacies")
    op.drop_table("recruitment_candidates")
    op.drop_table("postings")
