from tests.conftest import issue_token


def test_health(api_client):
    resp = api_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"service": "birthday-api", "status": "healthy"}


def test_metadata(api_client):
    resp = api_client.get("/api/birthday/metadata")
    assert resp.status_code == 200
    body = resp.json()
    assert body["key"] == "birthday"
    assert body["product_status"] == "COMING_SOON"


def test_summary(api_client):
    resp = api_client.get("/api/birthday/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "birthday-api"
    assert body["status"] == "healthy"
    assert body["product_status"] == "COMING_SOON"


def test_whoami_requires_a_valid_platform_core_token(api_client):
    resp = api_client.get("/api/birthday/whoami")
    assert resp.status_code == 401

    resp = api_client.get(
        "/api/birthday/whoami", headers={"Authorization": f"Bearer {issue_token(7, 'Someone')}"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"user_id": 7, "full_name": "Someone"}
