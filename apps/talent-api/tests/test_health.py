def test_health(api_client, db):
    resp = api_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"service": "talent-api", "status": "healthy"}


def test_health_deep_reports_recruitment_source_non_fatally(api_client, db):
    """recruitment-api is unreachable in the test process (no such service
    running); the check must degrade the READING, never break readiness or
    500 — a source-domain outage must not take talent-api out of rotation."""
    resp = api_client.get("/health/deep")
    assert resp.status_code == 200
    body = resp.json()
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["recruitment_source"] == "degraded"
