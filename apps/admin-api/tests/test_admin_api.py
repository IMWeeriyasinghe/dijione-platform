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


def test_users_list_is_enriched_with_client_names(api_client):
    resp = api_client.get("/api/admin/users", headers=VALID)
    assert resp.status_code == 200
    user = resp.json()[0]
    scope = user["module_assignments"][0]["client_scope"]
    assert scope["client_ids"] == [1]
    assert scope["client_names"] == ["ABC Company"]  # resolved via talent-api stub


def test_platform_core_403_is_forwarded(api_client):
    resp = api_client.get("/api/admin/users", headers=INVALID)
    assert resp.status_code == 403


def test_platform_core_404_is_forwarded(api_client):
    resp = api_client.get("/api/admin/users/999", headers=VALID)
    assert resp.status_code == 404


def test_missing_bearer_token_is_rejected_locally(api_client):
    resp = api_client.get("/api/admin/users")
    assert resp.status_code == 401


def test_clients_endpoint_forwards_talent_api(api_client):
    resp = api_client.get("/api/admin/clients", headers=VALID)
    assert resp.status_code == 200
    names = {c["name"] for c in resp.json()}
    assert names == {"ABC Company", "XYZ Company"}


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
    managing users — client names/counts degrade to empty/zero instead. This
    intentionally breaks *only* talent-api, reusing the real stub platform
    app so the platform-side response stays realistic."""
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
        assert scope["client_names"] == ["1"]  # degraded: id shown, not resolved to a name — not broken

        resp = client.get("/api/admin/dashboard", headers=VALID)
        assert resp.status_code == 200
        assert resp.json()["pending_talent_requests"] == 0
    finally:
        app.dependency_overrides.clear()
        platform_httpx.close()
