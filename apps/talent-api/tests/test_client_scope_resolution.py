"""Wave A / A2 — a client-scope claim carrying the durable platform
``Client.public_id`` (client_public_id / client_public_ids) is resolved to
DijiTalentFlow's own local integer client id before any tenant filtering
runs (Architecture Completion Plan §6.1). Legacy integer claims still work.
"""

from app.schemas.talent_request import TalentRequestCreate
from app.services.talent_request_service import TalentRequestService
from tests.conftest import headers_for


def _seed_request(db, client_id: int, designation: str) -> None:
    TalentRequestService(db).create_request(
        client_id=client_id,
        created_by=999,
        payload=TalentRequestCreate(designation=designation, description="d", required_skills=["x"]),
    )
    db.commit()


def test_public_id_claim_resolves_to_local_tenant(api_client, db, two_tenant_world):
    _seed_request(db, two_tenant_world["abc"].id, "ABC Only Role")
    _seed_request(db, two_tenant_world["xyz"].id, "XYZ Only Role")

    headers = headers_for(
        201, full_name="ABC via public id", role="TALENT_CLIENT",
        client_public_id="cli-abc-company", client_public_ids=["cli-abc-company"],
    )
    resp = api_client.get("/api/talent/requests", headers=headers)
    assert resp.status_code == 200, resp.text
    designations = {r["designation"] for r in resp.json()}
    assert designations == {"ABC Only Role"}  # never sees XYZ's tenant


def test_unknown_public_id_fails_closed(api_client, db, two_tenant_world):
    _seed_request(db, two_tenant_world["abc"].id, "ABC Only Role")
    headers = headers_for(
        202, full_name="ghost", role="TALENT_CLIENT",
        client_public_id="cli-not-synced-here", client_public_ids=["cli-not-synced-here"],
    )
    # No local clients row -> scope.client_id is None -> the client
    # dashboard 403s rather than falling through to another tenant.
    resp = api_client.get("/api/talent/dashboard/client", headers=headers)
    assert resp.status_code == 403


def test_legacy_integer_claim_still_works(api_client, db, two_tenant_world):
    _seed_request(db, two_tenant_world["xyz"].id, "XYZ Legacy Role")
    headers = headers_for(203, full_name="XYZ legacy", role="TALENT_CLIENT", client_id=two_tenant_world["xyz"].id)
    resp = api_client.get("/api/talent/requests", headers=headers)
    assert resp.status_code == 200, resp.text
    assert {r["designation"] for r in resp.json()} == {"XYZ Legacy Role"}
