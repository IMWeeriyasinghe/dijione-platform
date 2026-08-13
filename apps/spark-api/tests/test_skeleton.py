from tests.conftest import issue_token


def test_health(api_client):
    resp = api_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"service": "spark-api", "status": "healthy"}


def test_metadata(api_client):
    resp = api_client.get("/api/spark/metadata")
    assert resp.status_code == 200
    body = resp.json()
    assert body["key"] == "spark"
    assert body["product_status"] == "COMING_SOON"


def test_summary(api_client):
    resp = api_client.get("/api/spark/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "spark-api"
    assert body["status"] == "healthy"
    assert body["product_status"] == "COMING_SOON"


def test_whoami_requires_a_valid_platform_core_token(api_client):
    resp = api_client.get("/api/spark/whoami")
    assert resp.status_code == 401

    resp = api_client.get(
        "/api/spark/whoami", headers={"Authorization": f"Bearer {issue_token(9, 'Someone Else')}"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"user_id": 9, "full_name": "Someone Else"}
