def test_health(api_client, db):
    resp = api_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"service": "talent-api", "status": "healthy"}
