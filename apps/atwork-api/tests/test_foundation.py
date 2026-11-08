from tests.conftest import bearer, issue_token

ATWORK_ROLE = {
    "atwork": {
        "role": "TEST_ROLE",
        "client_id": None,
        "client_ids": None,
        "permissions": ["atwork.z", "atwork.a"],
    }
}


def test_health(api_client):
    resp = api_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"service": "atwork-api", "status": "healthy"}


def test_health_deep_reports_mode_and_no_database(api_client):
    body = api_client.get("/health/deep").json()
    assert body["status"] == "healthy"
    assert body["checks"] == {"app_env": "test", "integrations_mode": "mock", "database": "none (foundation)"}


def test_metadata(api_client):
    body = api_client.get("/api/atwork/metadata").json()
    assert body["key"] == "atwork"
    assert body["name"] == "DijiAtWork"
    assert body["product_status"] == "COMING_SOON"


def test_summary(api_client):
    assert api_client.get("/api/atwork/summary").json() == {
        "service": "atwork-api",
        "status": "healthy",
        "product_status": "COMING_SOON",
    }


def test_me_returns_role_and_sorted_permissions(api_client):
    resp = api_client.get("/api/atwork/me", headers=bearer(issue_token(module_roles=ATWORK_ROLE)))
    assert resp.status_code == 200
    assert resp.json() == {
        "user_id": 7,
        "full_name": "Test User",
        "module_access": True,
        "role": "TEST_ROLE",
        "permissions": ["atwork.a", "atwork.z"],
    }


def test_me_without_a_module_role_grants_nothing(api_client):
    other_module = {"other": {"role": "X", "client_id": None, "client_ids": None, "permissions": ["other.read"]}}
    body = api_client.get("/api/atwork/me", headers=bearer(issue_token(module_roles=other_module))).json()
    assert body["module_access"] is False
    assert body["role"] is None
    assert body["permissions"] == []


def test_me_does_not_expose_email(api_client):
    assert "email" not in api_client.get("/api/atwork/me", headers=bearer(issue_token())).json()


def test_me_requires_a_token(api_client):
    assert api_client.get("/api/atwork/me").status_code == 401


def test_me_rejects_invalid_credentials(api_client):
    bad_tokens = [
        "not-a-jwt",
        issue_token(secret="a-different-signing-secret"),
        issue_token(issuer="someone-else"),
        issue_token(expires_in_minutes=-1),
        issue_token(is_active=False),
    ]
    for token in bad_tokens:
        assert api_client.get("/api/atwork/me", headers=bearer(token)).status_code == 401


def test_cors_allows_only_listed_origins(api_client):
    allowed = api_client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    denied = api_client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in denied.headers


def test_correlation_id_is_echoed_and_generated(api_client):
    echoed = api_client.get("/health", headers={"X-Correlation-Id": "abc-123"})
    assert echoed.headers["x-correlation-id"] == "abc-123"
    assert api_client.get("/health").headers["x-correlation-id"]
