def test_health(api_client):
    assert api_client.get("/health").json() == {"service": "onsite-api", "status": "healthy"}


def test_health_deep(api_client, db):
    body = api_client.get("/health/deep").json()
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["integrations_mode"] == "mock"
