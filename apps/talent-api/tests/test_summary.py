"""CR §15: DijiOne Home's per-module status card. Unauthenticated by
design — aggregate counts only."""

from app.schemas.talent_request import TalentRequestCreate
from app.services.talent_request_service import TalentRequestService


def test_summary_is_unauthenticated_and_shaped(api_client, db):
    resp = api_client.get("/api/talent/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "talent-api"
    assert body["status"] == "healthy"
    assert body["pending_requests"] == 0


def test_summary_reflects_pending_requests(api_client, db, two_tenant_world):
    service = TalentRequestService(db)
    service.create_request(
        client_id=two_tenant_world["abc"].id, created_by=two_tenant_world["abc_user_id"],
        payload=TalentRequestCreate(designation="Role", description="d", required_skills=["x"]),
    )
    db.commit()

    resp = api_client.get("/api/talent/summary")
    assert resp.json()["pending_requests"] == 1
