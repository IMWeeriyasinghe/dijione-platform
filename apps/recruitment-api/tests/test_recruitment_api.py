"""The canonical Recruitment Source API — internal-token gated, exposes
postings (with the parsed governed DTC tag as a fact), candidacies,
freshness, and the 202 single-flight ad-hoc sync.
"""

import json

from app.models.posting import Posting
from app.services.recruitment_sync_service import RecruitmentSyncService
from tests.conftest import internal_headers


def _seed_posting(db, *, lever_id="post-x", title="Role", tags=None) -> Posting:
    p = Posting(
        lever_posting_id=lever_id, title=title, state="published",
        tags=json.dumps(tags or []),
    )
    db.add(p)
    db.commit()
    return p


def test_endpoints_require_internal_token(api_client, db):
    for path in ("/api/recruitment/postings", "/api/recruitment/freshness", "/api/recruitment/candidacies"):
        assert api_client.get(path).status_code == 401
    assert api_client.post("/api/recruitment/internal/sync", json={}).status_code == 401


def test_list_postings_exposes_dtc_tag_fact(api_client, db):
    _seed_posting(db, lever_id="p-am", title="AI Solutions Engineer", tags=["DTC - Agent Maestro"])
    _seed_posting(db, lever_id="p-plain", title="Plain Role", tags=["Remote"])

    resp = api_client.get("/api/recruitment/postings", headers=internal_headers())
    assert resp.status_code == 200
    by_id = {p["external_id"]: p for p in resp.json()}

    am = by_id["p-am"]
    assert am["dtc_tag"]["status"] == "OK"
    assert am["dtc_tag"]["client_name"] == "Agent Maestro"

    plain = by_id["p-plain"]
    assert plain["dtc_tag"]["status"] == "NO_TAG"
    assert plain["dtc_tag"]["client_name"] is None


def test_get_posting_by_external_id(api_client, db):
    _seed_posting(db, lever_id="p-1", title="Only One")
    assert api_client.get("/api/recruitment/postings/p-1", headers=internal_headers()).json()["title"] == "Only One"
    assert api_client.get("/api/recruitment/postings/nope", headers=internal_headers()).status_code == 404


def test_candidacies_after_mock_sync(api_client, db):
    # run a full mock sync via the service, then read the API
    from app.models.sync_run import RecruitmentSyncRun, SyncStatus, SyncTriggerType

    run = RecruitmentSyncRun(
        run_id="r1", provider="LEVER", trigger_type=SyncTriggerType.AD_HOC.value,
        requested_by_application="talent-flow", status=SyncStatus.QUEUED.value,
    )
    db.add(run)
    db.commit()
    RecruitmentSyncService.execute_run("r1")

    resp = api_client.get("/api/recruitment/candidacies", headers=internal_headers())
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 2
    assert all(r["candidate_external_id"] == "contact-ron-axel" for r in rows)
    assert {r["posting_external_id"] for r in rows} == {"post-senior-ppd", "post-senior-py"}


def test_ad_hoc_sync_is_202_and_single_flight(api_client, db):
    first = api_client.post(
        "/api/recruitment/internal/sync", json={"requested_by_user_id": 7}, headers=internal_headers()
    )
    assert first.status_code == 202
    body = first.json()
    assert body["started"] is True
    assert body["run_id"]

    # a second request while the first run is still QUEUED/RUNNING coalesces
    from app.models.sync_run import RecruitmentSyncRun, SyncStatus

    db.query(RecruitmentSyncRun).filter_by(run_id=body["run_id"]).update(
        {"status": SyncStatus.RUNNING.value}
    )
    db.commit()
    second = api_client.post("/api/recruitment/internal/sync", json={}, headers=internal_headers())
    assert second.status_code == 202
    assert second.json()["started"] is False
    assert second.json()["run_id"] == body["run_id"]
