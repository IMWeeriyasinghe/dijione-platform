"""DijiTalentFlow consuming the Recruitment Source domain over HTTP.

Covers the projection refresh + DTC reconciliation, and — critically — the
failure-injection guarantee: recruitment-api DOWN must not break the
TalentFlow workspace, leak across clients, or 500.
"""

from app.models.recruitment_posting_ref import RecruitmentPostingRef
from app.repositories.posting_client_mapping_repo import PostingClientMappingRepository
from app.services.recruitment_consumer_service import RecruitmentConsumerService
from tests.conftest import FakeRecruitmentClient, recruitment_posting_dto


def test_refresh_upserts_projection_and_reconciles_dtc(db, two_tenant_world, platform_calls):
    name = two_tenant_world["abc"].name
    dtos = [
        recruitment_posting_dto("p-am", title="AI Solutions Engineer",
                                dtc_status="OK", dtc_client_name=name, dtc_raw_tag=f"DTC - {name}"),
        recruitment_posting_dto("p-plain", title="Plain"),
    ]
    svc = RecruitmentConsumerService(db, client=FakeRecruitmentClient(dtos))
    result = svc.refresh_projection_and_reconcile()

    assert result["refreshed"] is True
    assert result["postings_seen"] == 2
    assert result["resolved"] == 1

    refs = {r.external_id: r for r in db.query(RecruitmentPostingRef).all()}
    assert set(refs) == {"p-am", "p-plain"}
    assert refs["p-am"].dtc_status == "OK" and refs["p-am"].dtc_client_name == name

    m = PostingClientMappingRepository(db).get_for_posting("p-am")
    assert m.status == "VERIFIED" and m.client_id == two_tenant_world["abc"].id and m.source == "LEVER_DTC_TAG"


def test_refresh_is_idempotent(db, two_tenant_world, platform_calls):
    dtos = [recruitment_posting_dto("p1")]
    svc = RecruitmentConsumerService(db, client=FakeRecruitmentClient(dtos))
    svc.refresh_projection_and_reconcile()
    svc.refresh_projection_and_reconcile()
    assert db.query(RecruitmentPostingRef).count() == 1


def test_source_down_is_a_safe_noop(db, two_tenant_world, platform_calls):
    # seed a last-good projection first
    RecruitmentConsumerService(
        db, client=FakeRecruitmentClient([recruitment_posting_dto("p1", title="Kept")])
    ).refresh_projection_and_reconcile()

    down = RecruitmentConsumerService(db, client=FakeRecruitmentClient(down=True))
    assert down.refresh_projection_and_reconcile() == {"refreshed": False, "reason": "source_unavailable"}
    assert down.freshness() == {"available": False, "provider": "LEVER", "last_successful_sync_at": None}
    # projection is untouched
    assert [r.title for r in db.query(RecruitmentPostingRef).all()] == ["Kept"]


def test_ad_hoc_sync_route_proxies_and_audits(api_client, db, two_tenant_world, platform_calls, monkeypatch):
    fake = FakeRecruitmentClient([])
    monkeypatch.setattr(
        "app.services.recruitment_consumer_service.get_recruitment_client", lambda: fake
    )
    monkeypatch.setattr("app.api.routes.recruitment.get_recruitment_client", lambda: fake)

    resp = api_client.post(
        "/api/talent/integrations/recruitment/sync", headers=two_tenant_world["ta_headers"]
    )
    assert resp.status_code == 202
    assert resp.json()["run_id"] == "run-fake"
    assert fake.sync_calls == [{"user": two_tenant_world["ta_user_id"]}]
    assert any(
        e["action"] == "recruitment.sync_requested" for e in platform_calls["audit_events"]
    )


def test_ad_hoc_sync_route_502_when_source_down(api_client, db, two_tenant_world, platform_calls, monkeypatch):
    fake = FakeRecruitmentClient(down=True)
    monkeypatch.setattr(
        "app.services.recruitment_consumer_service.get_recruitment_client", lambda: fake
    )
    resp = api_client.post(
        "/api/talent/integrations/recruitment/sync", headers=two_tenant_world["ta_headers"]
    )
    assert resp.status_code == 502


def test_freshness_route_degrades_when_source_down(api_client, db, two_tenant_world, platform_calls, monkeypatch):
    monkeypatch.setattr(
        "app.services.recruitment_consumer_service.get_recruitment_client",
        lambda: FakeRecruitmentClient(down=True),
    )
    resp = api_client.get(
        "/api/talent/integrations/recruitment/freshness", headers=two_tenant_world["ta_headers"]
    )
    assert resp.status_code == 200
    assert resp.json()["available"] is False
