"""Mock-mode end-to-end reconciliation: RecruitmentSyncService pulls Lever
postings + opportunities into the source read model. No Lever credential,
no network (INTEGRATIONS_MODE=mock).
"""

import uuid

import pytest

from app.models.posting import Posting
from app.models.recruitment_candidacy import RecruitmentCandidacy
from app.models.recruitment_candidate import RecruitmentCandidate
from app.models.sync_run import RecruitmentSyncRun, SyncStatus, SyncTriggerType
from app.services.lever_posting_service import (
    LeverPostingSyncService,
    MockSyncAgainstRealDataError,
)
from app.services.recruitment_sync_service import RecruitmentSyncService


def _queued_run(db) -> str:
    run_id = str(uuid.uuid4())
    db.add(
        RecruitmentSyncRun(
            run_id=run_id, provider="LEVER", trigger_type=SyncTriggerType.AD_HOC.value,
            requested_by_application="talent-flow", status=SyncStatus.QUEUED.value,
        )
    )
    db.commit()
    return run_id


def test_execute_run_ingests_postings_and_candidacies(db):
    run_id = _queued_run(db)
    RecruitmentSyncService.execute_run(run_id)

    db.expire_all()
    postings = db.query(Posting).all()
    assert {p.title for p in postings} == {
        "Senior Power Platform Developer",
        "Senior Python Developer",
        "Cloud Solutions Architect",
    }
    candidates = db.query(RecruitmentCandidate).all()
    assert [c.lever_contact_id for c in candidates] == ["contact-ron-axel"]  # one person, keyed on contact
    candidacies = db.query(RecruitmentCandidacy).all()
    assert len(candidacies) == 2  # Ron Axel has two opportunities

    run = db.query(RecruitmentSyncRun).filter_by(run_id=run_id).one()
    assert run.status == SyncStatus.SUCCEEDED.value
    assert run.completed_at is not None
    assert run.records_created >= 5


def test_execute_run_is_idempotent(db):
    RecruitmentSyncService.execute_run(_queued_run(db))
    RecruitmentSyncService.execute_run(_queued_run(db))
    db.expire_all()
    assert db.query(Posting).count() == 3
    assert db.query(RecruitmentCandidate).count() == 1
    assert db.query(RecruitmentCandidacy).count() == 2


def test_freshness_reflects_last_success(db):
    RecruitmentSyncService.execute_run(_queued_run(db))
    fresh = RecruitmentSyncService(db).freshness()
    assert fresh["provider"] == "LEVER"
    assert fresh["last_successful_sync_at"] is not None
    assert fresh["latest_run"]["status"] == SyncStatus.SUCCEEDED.value


def test_mock_posting_sync_refuses_to_run_against_real_data(db):
    """A mock-mode sync must not write fixture postings into a DB that
    already holds real, live-synced postings (a non-fixture lever id)."""
    db.add(
        Posting(
            lever_posting_id="c4552896-f3dd-45ad-8ebc-5f9b92ee64bb",  # real Lever UUID shape
            title="L3 Engineer (Network, Security and Systems)",
            state="closed",
        )
    )
    db.commit()

    with pytest.raises(MockSyncAgainstRealDataError):
        LeverPostingSyncService(db).sync_postings()

    db.expire_all()
    # No fixture postings were written, the real row is untouched.
    assert db.query(Posting).count() == 1
    assert {p.title for p in db.query(Posting).all()} == {
        "L3 Engineer (Network, Security and Systems)"
    }


def test_execute_run_marks_failed_when_mock_guard_trips(db):
    """The guard surfaces through the normal sync-run lifecycle as a clean
    FAILED run with a safe error summary — it never crashes the worker."""
    db.add(Posting(lever_posting_id="real-uuid-xyz", title="Real Role", state="published"))
    db.commit()

    run_id = _queued_run(db)
    RecruitmentSyncService.execute_run(run_id)

    db.expire_all()
    run = db.query(RecruitmentSyncRun).filter_by(run_id=run_id).one()
    assert run.status == SyncStatus.FAILED.value
    assert run.error_summary
    assert db.query(Posting).count() == 1  # nothing new written
