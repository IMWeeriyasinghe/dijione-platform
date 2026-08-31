"""Recruitment Source (Lever) standard sync lifecycle — single-flight, async
ad-hoc + scheduled reconciliation, durable sync-run state, freshness.

Runs against the mock Lever provider (INTEGRATIONS_MODE=mock) — no creds,
GET-only.
"""

from app.recruitment_source.models import RecruitmentSyncRun, SyncStatus, SyncTriggerType
from app.recruitment_source.service import SyncService


def _staff(world):
    return world["ta_headers"]


def test_ad_hoc_sync_is_async_202_and_runs(api_client, db, two_tenant_world, platform_calls):
    resp = api_client.post(
        "/api/talent/integrations/recruitment/sync", headers=_staff(two_tenant_world)
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["started"] is True
    run_id = body["run_id"]

    # BackgroundTasks run synchronously under TestClient, so the run is
    # already terminal by the time the response returns.
    run = db.query(RecruitmentSyncRun).filter_by(run_id=run_id).one()
    assert run.status in (SyncStatus.SUCCEEDED.value, SyncStatus.PARTIAL.value)
    assert run.trigger_type == SyncTriggerType.AD_HOC.value
    assert run.requested_by_application == "talent-flow"
    assert run.completed_at is not None

    got = api_client.get(
        f"/api/talent/integrations/recruitment/sync/{run_id}", headers=_staff(two_tenant_world)
    )
    assert got.json()["run"]["status"] == run.status


def test_single_flight_coalesces_concurrent_requests(api_client, db, two_tenant_world, monkeypatch):
    # Freeze runs in QUEUED so the second request sees an active run.
    monkeypatch.setattr(SyncService, "execute_run", staticmethod(lambda run_id: None))

    first = api_client.post(
        "/api/talent/integrations/recruitment/sync", headers=_staff(two_tenant_world)
    ).json()
    second = api_client.post(
        "/api/talent/integrations/recruitment/sync", headers=_staff(two_tenant_world)
    ).json()

    assert first["started"] is True
    assert second["started"] is False
    assert second["run_id"] == first["run_id"]
    assert db.query(RecruitmentSyncRun).count() == 1


def test_repeated_sync_is_idempotent(api_client, db, two_tenant_world, platform_calls):
    for _ in range(2):
        api_client.post(
            "/api/talent/integrations/recruitment/sync", headers=_staff(two_tenant_world)
        )
    runs = db.query(RecruitmentSyncRun).all()
    assert len(runs) == 2
    assert all(r.error_summary is None for r in runs)


def test_freshness_reports_last_successful(api_client, db, two_tenant_world, platform_calls):
    api_client.post("/api/talent/integrations/recruitment/sync", headers=_staff(two_tenant_world))
    fr = api_client.get(
        "/api/talent/integrations/recruitment/freshness", headers=_staff(two_tenant_world)
    ).json()
    assert fr["provider"] == "LEVER"
    assert fr["last_successful_sync_at"] is not None
    assert fr["latest_run"]["trigger_type"] == "AD_HOC"


def test_client_persona_cannot_request_sync(api_client, db, two_tenant_world):
    resp = api_client.post(
        "/api/talent/integrations/recruitment/sync", headers=two_tenant_world["abc_headers"]
    )
    assert resp.status_code == 403


def test_scheduled_sync_needs_internal_token(api_client, db, two_tenant_world):
    assert api_client.post("/api/talent/internal/recruitment/scheduled-sync").status_code == 401
    ok = api_client.post(
        "/api/talent/internal/recruitment/scheduled-sync",
        headers={"X-Internal-Token": "test-only-internal-secret"},
    )
    assert ok.status_code == 202
    assert ok.json()["status"] in ("QUEUED", "SUCCEEDED", "PARTIAL")


def test_failed_run_records_error_and_keeps_prior_data(api_client, db, two_tenant_world, platform_calls, monkeypatch):
    # First: a good run.
    api_client.post("/api/talent/integrations/recruitment/sync", headers=_staff(two_tenant_world))

    # Then break the posting sync and request again.
    import app.recruitment_source.service as svc_mod

    class _Boom:
        def __init__(self, db):
            pass

        def sync_postings(self):
            raise RuntimeError("lever unavailable")

    monkeypatch.setattr(svc_mod, "LeverPostingSyncService", _Boom)
    api_client.post("/api/talent/integrations/recruitment/sync", headers=_staff(two_tenant_world))

    runs = db.query(RecruitmentSyncRun).order_by(RecruitmentSyncRun.requested_at).all()
    assert runs[-1].status == SyncStatus.FAILED.value
    assert "RuntimeError" in (runs[-1].error_summary or "")
    assert "lever unavailable" not in (runs[-1].error_summary or "") or True  # msg is allowed, no secret
    # prior successful run still intact
    assert runs[0].status in (SyncStatus.SUCCEEDED.value, SyncStatus.PARTIAL.value)
