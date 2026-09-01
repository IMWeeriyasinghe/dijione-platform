def test_health(api_client):
    resp = api_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"service": "recruitment-api", "status": "healthy"}


def test_health_deep(api_client, db):
    resp = api_client.get("/health/deep")
    assert resp.status_code == 200
    body = resp.json()
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["integrations_mode"] == "mock"
