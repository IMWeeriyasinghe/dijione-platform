"""Mandatory MVP security requirement (CLAUDE.md §14): Client A must never
be able to reach Client B's records via list, detail, manipulated route ID,
or search/filter endpoints."""

from app.schemas.talent_request import TalentRequestCreate
from app.services.talent_request_service import TalentRequestService
from tests.conftest import auth_headers


def _create_requests(db, world):
    service = TalentRequestService(db)
    abc_request = service.create_request(
        client_id=world["abc"].id, created_by=world["abc_user"].id,
        payload=TalentRequestCreate(designation="ABC Role", description="d", required_skills=["x"]),
    )
    xyz_request = service.create_request(
        client_id=world["xyz"].id, created_by=world["xyz_user"].id,
        payload=TalentRequestCreate(designation="XYZ Role", description="d", required_skills=["x"]),
    )
    db.commit()
    return abc_request, xyz_request


def test_list_endpoint_is_tenant_scoped(api_client, db, two_tenant_world):
    abc_request, xyz_request = _create_requests(db, two_tenant_world)
    headers = auth_headers(api_client, "test-abc-client")

    resp = api_client.get("/api/talent/requests", headers=headers)
    assert resp.status_code == 200
    ids = {r["id"] for r in resp.json()}
    assert abc_request.id in ids
    assert xyz_request.id not in ids


def test_detail_endpoint_blocks_cross_tenant_access(api_client, db, two_tenant_world):
    abc_request, xyz_request = _create_requests(db, two_tenant_world)
    headers = auth_headers(api_client, "test-abc-client")

    own = api_client.get(f"/api/talent/requests/{abc_request.id}", headers=headers)
    assert own.status_code == 200

    other = api_client.get(f"/api/talent/requests/{xyz_request.id}", headers=headers)
    assert other.status_code == 404


def test_manipulated_route_id_is_blocked(api_client, db, two_tenant_world):
    """Directly guessing/incrementing another tenant's numeric ID must not
    leak data — this is the same check as above but explicit about intent:
    an attacker enumerating IDs sequentially gains nothing."""
    abc_request, xyz_request = _create_requests(db, two_tenant_world)
    headers = auth_headers(api_client, "test-xyz-client")

    for candidate_id in range(1, max(abc_request.id, xyz_request.id) + 2):
        resp = api_client.get(f"/api/talent/requests/{candidate_id}", headers=headers)
        if candidate_id == xyz_request.id:
            assert resp.status_code == 200
        else:
            assert resp.status_code in (404, 422)


def test_search_filter_endpoint_is_tenant_scoped(api_client, db, two_tenant_world):
    abc_request, xyz_request = _create_requests(db, two_tenant_world)
    headers = auth_headers(api_client, "test-abc-client")

    resp = api_client.get("/api/talent/requests", headers=headers, params={"search": "Role"})
    ids = {r["id"] for r in resp.json()}
    assert xyz_request.id not in ids

    # Attempting to force a cross-tenant client_id filter must not widen scope.
    resp = api_client.get(
        "/api/talent/requests", headers=headers, params={"client_id": two_tenant_world["xyz"].id}
    )
    ids = {r["id"] for r in resp.json()}
    assert xyz_request.id not in ids


def test_client_cannot_reach_staff_only_endpoints(api_client, db, two_tenant_world):
    headers = auth_headers(api_client, "test-abc-client")
    resp = api_client.get("/api/talent/candidates", headers=headers)
    assert resp.status_code == 403

    resp = api_client.get("/api/talent/clients", headers=headers)
    assert resp.status_code == 403


def test_staff_sees_all_tenants(api_client, db, two_tenant_world):
    abc_request, xyz_request = _create_requests(db, two_tenant_world)
    headers = auth_headers(api_client, "test-ta")

    resp = api_client.get("/api/talent/requests", headers=headers)
    ids = {r["id"] for r in resp.json()}
    assert abc_request.id in ids
    assert xyz_request.id in ids
