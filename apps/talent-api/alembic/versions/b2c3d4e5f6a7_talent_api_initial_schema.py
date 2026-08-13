"""talent-api initial schema

Phase 2.5 service separation: talent.db owns everything DijiTalentFlow-
specific — clients, talent requests, candidates, applications, interviews,
messages, documents, and the Lever/HubSpot integration tables. No table here
has a foreign key to `users` (Platform Core's own database owns User) —
``created_by``/``sender_id``/``uploaded_by`` are opaque ids, and
``messages.sender_name``/``documents.uploaded_by_name`` are captured at
write time instead of resolved by a cross-service join on every read. See
docs/platform/service-architecture.md "Data ownership across services".

Revision ID: b2c3d4e5f6a7
Revises:
Create Date: 2026-08-13 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("industry", sa.String(length=255), nullable=True),
        sa.Column("account_manager", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "candidates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=64), nullable=False),
        sa.Column("professional_title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=False),
        sa.Column("availability_status", sa.String(length=32), nullable=False),
        sa.Column("skills", sa.String(length=500), nullable=False),
        sa.Column("cv_reference", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("lever_external_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("candidates", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_candidates_email"), ["email"], unique=True)
        batch_op.create_index(batch_op.f("ix_candidates_lever_external_id"), ["lever_external_id"], unique=False)

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
        sa.UniqueConstraint("provider", "external_object_type", "external_id", name="uq_external_object"),
    )
    with op.batch_alter_table("external_mappings", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_external_mappings_external_id"), ["external_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_external_mappings_internal_id"), ["internal_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_external_mappings_provider"), ["provider"], unique=False)

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
    with op.batch_alter_table("integration_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_integration_events_provider"), ["provider"], unique=False)

    op.create_table(
        "talent_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_code", sa.String(length=32), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("designation", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("required_skills", sa.String(length=500), nullable=False),
        sa.Column("seniority", sa.String(length=64), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=False),
        sa.Column("engagement_type", sa.String(length=32), nullable=False),
        sa.Column("target_start_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("current_stage", sa.String(length=32), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=32), nullable=False),
        sa.Column("customer_success_status", sa.String(length=32), nullable=False),
        sa.Column("ta_status", sa.String(length=32), nullable=False),
        sa.Column("client_safe_status_text", sa.String(length=255), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        # No FK to `users.id` — see module docstring.
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("talent_requests", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_talent_requests_client_id"), ["client_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_talent_requests_request_code"), ["request_code"], unique=True)

    op.create_table(
        "applications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("talent_request_id", sa.Integer(), nullable=False),
        sa.Column("current_stage", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("recruiter_notes", sa.Text(), nullable=False),
        sa.Column("client_visible_notes", sa.Text(), nullable=False),
        sa.Column("rejection_reason", sa.String(length=500), nullable=False),
        sa.Column("is_client_visible", sa.Boolean(), nullable=False),
        sa.Column("lever_opportunity_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["talent_request_id"], ["talent_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", "talent_request_id", name="uq_candidate_request"),
    )
    with op.batch_alter_table("applications", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_applications_candidate_id"), ["candidate_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_applications_talent_request_id"), ["talent_request_id"], unique=False)

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("talent_request_id", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        # No FK to `users.id` — see module docstring.
        sa.Column("uploaded_by", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_name", sa.String(length=255), nullable=False),
        sa.Column("storage_reference", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["talent_request_id"], ["talent_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_documents_talent_request_id"), ["talent_request_id"], unique=False)

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("talent_request_id", sa.Integer(), nullable=False),
        # No FK to `users.id` — see module docstring.
        sa.Column("sender_id", sa.Integer(), nullable=False),
        sa.Column("sender_name", sa.String(length=255), nullable=False),
        sa.Column("sender_role", sa.String(length=64), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["talent_request_id"], ["talent_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_messages_talent_request_id"), ["talent_request_id"], unique=False)

    op.create_table(
        "interviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interview_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("meeting_link", sa.String(length=500), nullable=False),
        sa.Column("client_visible", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("interviews", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_interviews_application_id"), ["application_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("interviews", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_interviews_application_id"))
    op.drop_table("interviews")
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_messages_talent_request_id"))
    op.drop_table("messages")
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_documents_talent_request_id"))
    op.drop_table("documents")
    with op.batch_alter_table("applications", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_applications_talent_request_id"))
        batch_op.drop_index(batch_op.f("ix_applications_candidate_id"))
    op.drop_table("applications")
    with op.batch_alter_table("talent_requests", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_talent_requests_request_code"))
        batch_op.drop_index(batch_op.f("ix_talent_requests_client_id"))
    op.drop_table("talent_requests")
    with op.batch_alter_table("integration_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_integration_events_provider"))
    op.drop_table("integration_events")
    with op.batch_alter_table("external_mappings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_external_mappings_provider"))
        batch_op.drop_index(batch_op.f("ix_external_mappings_internal_id"))
        batch_op.drop_index(batch_op.f("ix_external_mappings_external_id"))
    op.drop_table("external_mappings")
    op.drop_table("clients")
    with op.batch_alter_table("candidates", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_candidates_lever_external_id"))
        batch_op.drop_index(batch_op.f("ix_candidates_email"))
    op.drop_table("candidates")
