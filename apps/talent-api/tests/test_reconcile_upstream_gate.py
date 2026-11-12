"""Reconcile acts only on a complete source snapshot, and says so when it holds."""

import pytest

from app.models.application import Application
from app.models.candidate import Candidate
from app.models.posting_client_mapping import PostingClientMapping
from app.models.talent_request import TalentRequest
from app.services import recruitment_consumer_service as consumer
from tests.conftest import FakeRecruitmentClient, recruitment_candidacy_dto, recruitment_posting_dto

URL = "/api/talent/internal/recruitment/reconcile"
HEADERS = {"X-Internal-Token": "test-only-internal-secret"}


def _posting(client_name):
    return recruitment_posting_dto(
        "p1", title="Engineer", dtc_status="OK", dtc_client_name=client_name, dtc_raw_tag=f"DTC - {client_name}",
    )


def _candidacy(opp="opp-1", contact="contact-1"):
    return recruitment_candidacy_dto(opp, posting_external_id="p1", candidate_external_id=contact)


def _run(api_client, monkeypatch, source):
    monkeypatch.setattr("app.api.routes.recruitment.get_recruitment_batch_client", lambda: source)
    return api_client.post(URL, headers=HEADERS)


def _apps(db):
    db.expire_all()
    return db.query(Application).all()


def _seed(api_client, monkeypatch, name):
    source = FakeRecruitmentClient([_posting(name)], candidacies=[_candidacy()])
    assert _run(api_client, monkeypatch, source).status_code == 200


@pytest.mark.parametrize(
    ("state", "reason"),
    [
        ("INCOMPLETE", "upstream_incomplete"), ("FAILED", "upstream_failed"), ("STALE", "upstream_stale"),
        ("RUNNING", "upstream_running"), ("NONE", "upstream_never_synced"), (None, "upstream_incomplete"),
    ],
)
def test_anything_but_complete_holds_with_no_writes(api_client, db, two_tenant_world, monkeypatch, state, reason):
    source = FakeRecruitmentClient([_posting(two_tenant_world["abc"].name)], candidacies=[_candidacy()])
    source.source_snapshot = {"state": state, "client_postings_total": 63, "client_postings_unread": 56}
    resp = _run(api_client, monkeypatch, source)
    assert resp.status_code == 409
    body = resp.json()
    assert body["outcome"] == "SKIPPED" and body["fully_refreshed"] is False and body["reasons"] == [reason]
    assert body["counts"]["upstream"]["client_postings_unread"] == 56
    db.expire_all()
    assert db.query(TalentRequest).count() == 0 and db.query(PostingClientMapping).count() == 0


def test_an_older_source_without_a_snapshot_holds(api_client, db, two_tenant_world, monkeypatch):
    source = FakeRecruitmentClient([_posting(two_tenant_world["abc"].name)])
    source.source_snapshot = None
    assert _run(api_client, monkeypatch, source).json()["reasons"] == ["upstream_incomplete"]


def test_unreachable_source_holds(api_client, db, two_tenant_world, monkeypatch):
    source = FakeRecruitmentClient([_posting(two_tenant_world["abc"].name)], down=True)
    resp = _run(api_client, monkeypatch, source)
    assert resp.json()["reasons"] == ["source_unavailable"] and resp.status_code == 503


def test_complete_source_reconciles_and_new_applications_are_unshared(api_client, db, two_tenant_world, monkeypatch):
    _seed(api_client, monkeypatch, two_tenant_world["abc"].name)
    assert [a.is_client_visible for a in _apps(db)] == [False]


def test_held_run_does_not_retire_reassign_or_withdraw(api_client, db, two_tenant_world, monkeypatch):
    _seed(api_client, monkeypatch, two_tenant_world["abc"].name)
    application = _apps(db)[0]
    application.is_client_visible = True
    db.commit()
    request = db.query(TalentRequest).one()
    original = (request.client_id, request.provider)
    retagged = FakeRecruitmentClient([_posting(two_tenant_world["xyz"].name)])
    retagged.source_snapshot = {"state": "INCOMPLETE"}
    assert _run(api_client, monkeypatch, retagged).status_code == 409
    db.expire_all()
    request = db.query(TalentRequest).one()
    assert (request.client_id, request.provider) == original
    assert _apps(db)[0].is_client_visible is True


def test_retag_on_a_complete_snapshot_still_withdraws(api_client, db, two_tenant_world, monkeypatch):
    _seed(api_client, monkeypatch, two_tenant_world["abc"].name)
    _apps(db)[0].is_client_visible = True
    db.commit()
    retagged = FakeRecruitmentClient([_posting(two_tenant_world["xyz"].name)], candidacies=[_candidacy()])
    assert _run(api_client, monkeypatch, retagged).status_code == 200
    assert not any(a.is_client_visible and a.talent_request.client_id == two_tenant_world["xyz"].id for a in _apps(db))
    assert not any(a.is_client_visible for a in _apps(db))


def test_a_candidacy_missing_from_the_source_is_not_treated_as_deleted(api_client, db, two_tenant_world, monkeypatch):
    name = two_tenant_world["abc"].name
    _seed(api_client, monkeypatch, name)
    _apps(db)[0].is_client_visible = True
    db.commit()
    assert _run(api_client, monkeypatch, FakeRecruitmentClient([_posting(name)], candidacies=[])).status_code == 200
    applications = _apps(db)
    assert len(applications) == 1 and applications[0].is_client_visible is True
    assert db.query(Candidate).count() == 1


def test_a_retried_reconcile_creates_no_duplicates(api_client, db, two_tenant_world, monkeypatch):
    name = two_tenant_world["abc"].name
    _seed(api_client, monkeypatch, name)
    _seed(api_client, monkeypatch, name)
    db.expire_all()
    assert db.query(TalentRequest).count() == 1 and len(_apps(db)) == 1


def test_complete_coverage_from_a_partial_latest_run_is_not_reported_as_full_success(
    api_client, db, two_tenant_world, monkeypatch
):
    source = FakeRecruitmentClient([_posting(two_tenant_world["abc"].name)], candidacies=[_candidacy()])
    source.source_snapshot = {"state": "COMPLETE", "latest_run_status": "PARTIAL"}
    body = _run(api_client, monkeypatch, source).json()
    assert body["outcome"] == "PARTIAL" and body["fully_refreshed"] is False
    assert body["reasons"] == ["upstream_rolling_read"]
    assert [a.is_client_visible for a in _apps(db)] == [False]


def test_hold_is_audited(api_client, db, two_tenant_world, monkeypatch):
    logged = []
    monkeypatch.setattr(consumer.AuditService, "log", lambda self, **kw: logged.append(kw))
    source = FakeRecruitmentClient([_posting(two_tenant_world["abc"].name)])
    source.source_snapshot = {"state": "FAILED"}
    _run(api_client, monkeypatch, source)
    assert [e["action"] for e in logged] == ["recruitment.reconcile_held"]
    assert logged[0]["new_state"]["reason"] == "upstream_failed"
