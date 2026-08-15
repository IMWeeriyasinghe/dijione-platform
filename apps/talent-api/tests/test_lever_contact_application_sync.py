"""Contact/Opportunity -> Candidate/PostingApplication sync (CLAUDE.md §60
follow-on). Uses MockLeverClient (INTEGRATIONS_MODE=mock in conftest.py).

Critical invariants:
- Candidate identity is keyed off the Lever Contact id, never the
  Opportunity id — one Contact with multiple Opportunities must produce
  exactly one Candidate (CLAUDE.md §19).
- Never writes to the client-owned Application/TalentRequest tables.
- Never assigns a client to anything synced.
- Idempotent: repeated runs don't duplicate Candidates or
  PostingApplications.
"""

from sqlalchemy import select

from app.models.candidate import Candidate
from app.models.external_mapping import ExternalMapping
from app.models.posting_application import PostingApplication
from app.services.lever_contact_application_sync_service import LeverContactApplicationSyncService
from app.services.lever_posting_service import LeverPostingSyncService


def _sync_postings_then_opportunities(db):
    LeverPostingSyncService(db).sync_postings()
    db.commit()
    result = LeverContactApplicationSyncService(db).sync_opportunities()
    db.commit()
    return result


def test_one_contact_multiple_opportunities_produces_one_candidate(db, two_tenant_world):
    result = _sync_postings_then_opportunities(db)

    # MockLeverClient's fixture: two opportunities ("...ppd", "...py"),
    # both contact_id="contact-ron-axel".
    assert result["opportunities_seen"] == 2
    assert result["candidates_created"] == 1
    assert result["candidates_matched"] == 1  # second opportunity matches the first's candidate

    candidates = list(
        db.execute(select(Candidate).where(Candidate.lever_external_id == "contact-ron-axel")).scalars()
    )
    assert len(candidates) == 1

    posting_applications = list(
        db.execute(select(PostingApplication).where(PostingApplication.candidate_id == candidates[0].id)).scalars()
    )
    assert len(posting_applications) == 2  # one per opportunity, same candidate


def test_sync_creates_contact_external_mapping(db, two_tenant_world):
    _sync_postings_then_opportunities(db)

    mapping = db.execute(
        select(ExternalMapping).where(
            ExternalMapping.provider == "LEVER",
            ExternalMapping.external_object_type == "contact",
            ExternalMapping.external_id == "contact-ron-axel",
        )
    ).scalars().first()
    assert mapping is not None
    assert mapping.internal_object_type == "Candidate"


def test_repeated_sync_is_idempotent(db, two_tenant_world):
    first = _sync_postings_then_opportunities(db)
    assert first["candidates_created"] == 1
    assert first["posting_applications_created"] == 2

    second_result = LeverContactApplicationSyncService(db).sync_opportunities()
    db.commit()

    assert second_result["candidates_created"] == 0
    assert second_result["candidates_matched"] == 2
    assert second_result["posting_applications_created"] == 0
    assert second_result["posting_applications_updated"] == 2

    all_candidates = list(
        db.execute(select(Candidate).where(Candidate.lever_external_id == "contact-ron-axel")).scalars()
    )
    assert len(all_candidates) == 1
    all_pas = list(db.execute(select(PostingApplication)).scalars())
    assert len(all_pas) == 2


def test_sync_never_writes_client_owned_application_table(db, two_tenant_world):
    """The pre-existing seed `applications` table (Candidate<->TalentRequest,
    always client-owned) must be completely untouched by this sync."""
    from app.models.application import Application

    before = list(db.execute(select(Application)).scalars())
    _sync_postings_then_opportunities(db)
    after = list(db.execute(select(Application)).scalars())
    assert len(before) == len(after) == 0  # two_tenant_world seeds no Applications


def test_sync_assigns_no_client_to_anything(db, two_tenant_world):
    _sync_postings_then_opportunities(db)

    candidates = list(db.execute(select(Candidate)).scalars())
    assert len(candidates) == 1  # no client-scoping concept exists on Candidate at all

    posting_applications = list(db.execute(select(PostingApplication)).scalars())
    assert len(posting_applications) == 2
    # PostingApplication has no client_id column at all — structurally
    # incapable of carrying a client assignment.
    assert not hasattr(PostingApplication, "client_id")


def test_sync_opportunities_respects_limit(db, two_tenant_world):
    LeverPostingSyncService(db).sync_postings()
    db.commit()
    result = LeverContactApplicationSyncService(db).sync_opportunities(limit=1)
    db.commit()
    assert result["opportunities_seen"] == 1
