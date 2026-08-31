"""Mock-mode end-to-end reconciliation: RecruitmentSyncService pulls Lever
postings + opportunities into the source read model. No Lever credential,
no network (INTEGRATIONS_MODE=mock).
"""

import uuid

from app.models.posting import Posting
from app.models.recruitment_candidacy import RecruitmentCandidacy
from app.models.recruitment_candidate import RecruitmentCandidate
from app.models.sync_run import RecruitmentSyncRun, SyncStatus, SyncTriggerType
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
