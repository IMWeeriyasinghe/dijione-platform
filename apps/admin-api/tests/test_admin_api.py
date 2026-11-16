from auth_client_py import PlatformClient
from fastapi.testclient import TestClient

from app.main import app
from app.services import platform_gateway, talent_gateway

VALID = {"Authorization": "Bearer valid-admin-token"}
INVALID = {"Authorization": "Bearer not-an-admin"}


def test_dashboard_is_enriched_with_talent_pending_count(api_client):
    resp = api_client.get("/api/admin/dashboard", headers=VALID)
    assert resp.status_code == 200
    assert resp.json()["pending_talent_requests"] == 4  # from the talent-api stub


def test_users_list_carries_client_names_from_platform_core(api_client):
    resp = api_client.get("/api/admin/users", headers=VALID)
    assert resp.status_code == 200
    user = resp.json()[0]
    scope = user["module_assignments"][0]["client_scope"]
    assert scope["client_ids"] == [1]
    assert scope["client_names"] == ["ABC Company"]  # Platform Core resolves these (§6.1)


def test_platform_core_403_is_forwarded(api_client):
    resp = api_client.get("/api/admin/users", headers=INVALID)
    assert resp.status_code == 403


def test_platform_core_404_is_forwarded(api_client):
    resp = api_client.get("/api/admin/users/999", headers=VALID)
    assert resp.status_code == 404


def test_missing_bearer_token_is_rejected_locally(api_client):
    resp = api_client.get("/api/admin/users")
    assert resp.status_code == 401


def test_clients_endpoint_forwards_platform_api(api_client):
    resp = api_client.get("/api/admin/clients", headers=VALID)
    assert resp.status_code == 200
    names = {c["name"] for c in resp.json()}
    assert names == {"ABC Company", "XYZ Company"}
    assert {c["public_id"] for c in resp.json()} == {"cli-abc-company", "cli-xyz-company"}


def test_groups_endpoint_forwards_platform_api(api_client):
    resp = api_client.get("/api/admin/groups", headers=VALID)
    assert resp.status_code == 200
    assert resp.json()[0]["key"] == "ta-team"


def test_groups_endpoint_forwards_403(api_client):
    resp = api_client.get("/api/admin/groups", headers=INVALID)
    assert resp.status_code == 403


def test_application_detail_endpoint_is_enriched_with_client_names(api_client):
    resp = api_client.get("/api/admin/applications/talent-flow", headers=VALID)
    assert resp.status_code == 200
    scope = resp.json()["assigned_users"][0]["client_scope"]
    assert scope["client_ids"] == [1]
    assert scope["client_names"] == ["ABC Company"]


def test_health(api_client):
    resp = api_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"service": "admin-api", "status": "healthy"}


def test_health_deep_degrades_non_fatally_when_downstreams_are_unreachable(api_client):
    # No override wired here -> platform_api_url/talent_api_url point at
    # their localhost defaults, unreachable in the test process. The probe
    # must still return 200 with a "degraded" status, never 5xx.
    resp = api_client.get("/health/deep")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["checks"]["platform_api"] == "unreachable"
    assert body["checks"]["talent_api"] == "unreachable"


def test_platform_core_unavailable_returns_503():
    unreachable = PlatformClient(base_url="http://127.0.0.1:1", internal_secret="x", timeout=0.5)
    app.dependency_overrides[platform_gateway.get_platform_client] = lambda: unreachable
    app.dependency_overrides[talent_gateway.get_talent_client] = lambda: unreachable
    try:
        client = TestClient(app)
        resp = client.get("/api/admin/users", headers=VALID)
        assert resp.status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_talent_api_unavailable_degrades_admin_gracefully():
    """CR §38: a TalentFlow outage must not prevent an administrator from
    managing users. Client names now come from Platform Core (§6.1) so they
    are unaffected; only the dashboard's live pending-request count — the one
    remaining talent-api call — degrades to zero."""
    from tests.conftest import _build_stub_platform_app

    platform_httpx = TestClient(_build_stub_platform_app(), base_url="http://platform-api")
    platform_client = PlatformClient(base_url="http://platform-api", internal_secret="unused", client=platform_httpx)
    unreachable_talent = PlatformClient(base_url="http://127.0.0.1:1", internal_secret="x", timeout=0.5)

    app.dependency_overrides[platform_gateway.get_platform_client] = lambda: platform_client
    app.dependency_overrides[talent_gateway.get_talent_client] = lambda: unreachable_talent
    try:
        client = TestClient(app)
        resp = client.get("/api/admin/users", headers=VALID)
        assert resp.status_code == 200
        scope = resp.json()[0]["module_assignments"][0]["client_scope"]
        assert scope["client_ids"] == [1]
        assert scope["client_names"] == ["ABC Company"]  # from Platform Core, unaffected

        resp = client.get("/api/admin/dashboard", headers=VALID)
        assert resp.status_code == 200
        assert resp.json()["pending_talent_requests"] == 0  # only this degrades
    finally:
        app.dependency_overrides.clear()
        platform_httpx.close()


def test_create_user_is_forwarded_with_its_status_and_errors(api_client):
    created = api_client.post("/api/admin/users", json={"email": "new@example.com", "full_name": "New"}, headers=VALID)
    assert created.status_code == 201
    assert (created.json()["id"], created.json()["email"]) == (77, "new@example.com")

    taken = api_client.post("/api/admin/users", json={"email": "taken@example.com", "full_name": "T"}, headers=VALID)
    assert taken.status_code == 409
    assert "already exists" in taken.json()["detail"]

    denied = api_client.post("/api/admin/users", json={"email": "new@example.com", "full_name": "New"}, headers=INVALID)
    assert denied.status_code == 403


def test_directory_routes_are_forwarded(api_client):
    hits = api_client.get("/api/admin/directory/users", params={"q": "ana"}, headers=VALID)
    assert hits.status_code == 200 and hits.json()[0]["query"] == "ana"
    assert api_client.get("/api/admin/directory/users", params={"q": "a"}, headers=VALID).status_code == 422
    assert api_client.get("/api/admin/directory/users", params={"q": "ana"}, headers=INVALID).status_code == 403

    verified = api_client.post("/api/admin/users/9/verify-directory", headers=VALID)
    assert verified.status_code == 200 and verified.json()["directory_verified"] is True
    refused = api_client.post("/api/admin/users/400/verify-directory", headers=VALID)
    assert refused.status_code == 400 and "No directory account" in refused.json()["detail"]

    assert api_client.post("/api/admin/employee-records/reconcile", headers=VALID).json()["matched"] == 1
    groups = api_client.get("/api/admin/users/9/entra-groups", headers=VALID)
    assert groups.status_code == 200 and groups.json()[0]["display_name"] == "All Staff"


def test_adding_from_the_directory_passes_a_duplicate_through_with_its_existing_profile(api_client):
    created = api_client.post("/api/admin/users/from-directory", json={"entra_object_id": "oid-9"}, headers=VALID)
    assert created.status_code == 201 and created.json()["id"] == 88
    taken = api_client.post("/api/admin/users/from-directory", json={"entra_object_id": "taken"}, headers=VALID)
    assert taken.status_code == 409 and taken.json() == {"detail": "Already in DijiOne", "existing_user_id": 5}


def test_photos_are_passed_through_as_images(api_client):
    photo = api_client.get("/api/admin/directory/users/oid-1/photo", headers=VALID)
    assert photo.status_code == 200 and photo.content == b"\xff\xd8jpeg"
    assert photo.headers["content-type"] == "image/jpeg" and photo.headers["cache-control"] == "private, max-age=3600"
    assert api_client.get("/api/admin/directory/users/none/photo", headers=VALID).status_code == 404
    assert api_client.get("/api/admin/users/3/photo", headers=VALID).headers["content-type"] == "image/png"
    assert api_client.get("/api/admin/users/3/photo", headers=INVALID).status_code == 403


def test_audit_filters_are_forwarded_and_absent_ones_are_omitted(api_client):
    scoped = api_client.get("/api/admin/audit", params={"user_id": 42, "limit": 50}, headers=VALID)
    assert scoped.status_code == 200
    assert scoped.json()[0]["new_state"] == "[('limit', '50'), ('user_id', '42')]"

    by_entity = api_client.get("/api/admin/audit", params={"entity_type": "User", "entity_id": 7}, headers=VALID)
    assert by_entity.json()[0]["new_state"] == "[('entity_id', '7'), ('entity_type', 'User'), ('limit', '200')]"


def test_restore_default_access_is_forwarded_with_its_errors(api_client):
    assert api_client.post("/api/admin/users/1/modules/field-ops/restore-default", headers=VALID).status_code == 200
    assert api_client.post("/api/admin/users/1/modules/talent-flow/restore-default", headers=VALID).status_code == 404
    assert api_client.post("/api/admin/users/1/modules/field-ops/restore-default", headers=INVALID).status_code == 403


def test_access_diagnostics_is_forwarded_with_its_status_and_errors(api_client):
    ok = api_client.get("/api/admin/users/1/access-diagnostics", headers=VALID)
    assert ok.status_code == 200 and ok.json()["user_id"] == 1
    assert api_client.get("/api/admin/users/999/access-diagnostics", headers=VALID).status_code == 404
    assert api_client.get("/api/admin/users/1/access-diagnostics", headers=INVALID).status_code == 403
    assert api_client.get("/api/admin/users/1/access-diagnostics").status_code in (401, 403)


def test_view_as_start_and_end_are_forwarded_with_their_errors(api_client):
    started = api_client.post("/api/admin/view-as", json={"target_user_id": 5}, headers=VALID)
    assert started.status_code == 201 and started.json()["session_id"] == "S-1"
    assert api_client.post("/api/admin/view-as", json={"target_user_id": 404}, headers=VALID).status_code == 404
    assert api_client.post("/api/admin/view-as", json={"target_user_id": 5}, headers=INVALID).status_code == 403
    assert api_client.post("/api/admin/view-as/S-1/end", headers=VALID).json() == {"session_id": "S-1", "ended": True}
    assert api_client.post("/api/admin/view-as", json={"target_user_id": 5}).status_code in (401, 403)
