"""promote VERIFIED postings into TalentRequests/Candidates/Applications

DijiTalentFlow real-data completion, Phase A. Adds the columns + idempotency
indexes the new VerifiedPostingPromotionReconciler needs to turn a VERIFIED
PostingClientMapping into real TalentRequest/Candidate/Application rows,
traceable back to their Lever external ids.

- ``talent_requests`` gains ``provider`` + ``posting_external_id``: the
  source-relationship key, mirroring how ``posting_client_mappings`` is
  already keyed on ``(provider, posting_external_id)`` rather than a local
  FK (the posting read model lives in recruitment-api's database). A
  partial unique index enforces "one VERIFIED posting = one TalentRequest"
  without constraining the pre-existing, non-Lever-sourced rows (their
  ``posting_external_id`` stays NULL).
- ``candidates.email`` is relaxed from UNIQUE NOT NULL to a plain nullable
  index. Real Lever contacts can carry an explicit empty email; dedup for
  Lever-sourced candidates moves to ``lever_external_id`` (already present,
  vestigial until now), which gets its own partial unique index. The manual
  "Add Candidate" dedup-by-email flow (``CandidateRepository.get_by_email``
  + a 409 in the route) is unaffected — it is an app-level soft-dedup, not
  a DB constraint.
- ``applications.lever_opportunity_id`` gets a partial unique index for
  traceability + belt-and-braces idempotency; ``uq_candidate_request``
  (already present) stays the primary dedup key for the Application row
  itself.

All three indexes are partial (``WHERE ... IS NOT NULL``), supported on
both SQLite (>= 3.8) and PostgreSQL via the ``sqlite_where`` /
``postgresql_where`` dialect kwargs — a plain ``UniqueConstraint`` cannot be
partial.

Purely additive; downgrade is a real rollback (not a NotImplementedError
one-way migration like the Wave C table drops), but downgrading past a DB
that already holds promoted (NULL-email or NULL-posting-linked) rows will
fail on the NOT NULL restores — those rows must be removed first.

Revision ID: d2f4a6b8c0e1
Revises: c1d3e5f7a9b0
Create Date: 2026-09-02 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d2f4a6b8c0e1"
down_revision: Union[str, Sequence[str], None] = "c1d3e5f7a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- talent_requests: source-relationship key --------------------------
    with op.batch_alter_table("talent_requests", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("provider", sa.String(length=32), nullable=False, server_default="LEVER")
        )
        batch_op.add_column(
            sa.Column("posting_external_id", sa.String(length=128), nullable=True)
        )
    op.create_index(
        "uq_talent_requests_posting_ref",
        "talent_requests",
        ["provider", "posting_external_id"],
        unique=True,
        sqlite_where=sa.text("posting_external_id IS NOT NULL"),
        postgresql_where=sa.text("posting_external_id IS NOT NULL"),
    )

    # --- candidates: email relaxed, lever_external_id becomes the dedup key
    with op.batch_alter_table("candidates", schema=None) as batch_op:
        batch_op.drop_index("ix_candidates_email")
        batch_op.alter_column("email", existing_type=sa.String(length=255), nullable=True)
        batch_op.create_index("ix_candidates_email", ["email"], unique=False)
        batch_op.drop_index("ix_candidates_lever_external_id")
    op.create_index(
        "uq_candidates_lever_external_id",
        "candidates",
        ["lever_external_id"],
        unique=True,
        sqlite_where=sa.text("lever_external_id IS NOT NULL"),
        postgresql_where=sa.text("lever_external_id IS NOT NULL"),
    )

    # --- applications: traceability + belt-and-braces idempotency ---------
    op.create_index(
        "uq_applications_lever_opportunity_id",
        "applications",
        ["lever_opportunity_id"],
        unique=True,
        sqlite_where=sa.text("lever_opportunity_id IS NOT NULL"),
        postgresql_where=sa.text("lever_opportunity_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_applications_lever_opportunity_id", table_name="applications")

    op.drop_index("uq_candidates_lever_external_id", table_name="candidates")
    with op.batch_alter_table("candidates", schema=None) as batch_op:
        batch_op.create_index(
            "ix_candidates_lever_external_id", ["lever_external_id"], unique=False
        )
        batch_op.drop_index("ix_candidates_email")
        # Fails here if any promoted (NULL-email) candidate rows remain —
        # delete or backfill them before downgrading.
        batch_op.alter_column("email", existing_type=sa.String(length=255), nullable=False)
        batch_op.create_index("ix_candidates_email", ["email"], unique=True)

    op.drop_index("uq_talent_requests_posting_ref", table_name="talent_requests")
    with op.batch_alter_table("talent_requests", schema=None) as batch_op:
        batch_op.drop_column("posting_external_id")
        batch_op.drop_column("provider")
