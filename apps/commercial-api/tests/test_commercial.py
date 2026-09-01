import hashlib
import hmac

from tests.conftest import internal_headers


def test_health(api_client):
    resp = api_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"service": "commercial-api", "status": "healthy"}


def test_health_deep(api_client, db):
    resp = api_client.get("/health/deep")
    assert resp.status_code == 200
    assert resp.json()["checks"]["database"] == "ok"


def test_hubspot_status_requires_internal_token(api_client, db):
    assert api_client.get("/api/commercial/hubspot/status").status_code == 401


def test_hubspot_status_mock(api_client, db):
    resp = api_client.get("/api/commercial/hubspot/status", headers=internal_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "mock"
    assert body["companies_available"] > 0
    assert body["read_only"] is True


def test_hubspot_webhook_is_idempotent(api_client, db):
    payload = {"eventId": "evt-1", "subscriptionType": "company.propertyChange"}
    first = api_client.post("/api/commercial/webhooks/hubspot", json=payload)
    second = api_client.post("/api/commercial/webhooks/hubspot", json=payload)
    assert first.status_code == 200
    assert first.json()["status"] == "PROCESSED"
    assert second.json()["status"] == "IGNORED_DUPLICATE"
    assert second.json()["event_id"] == first.json()["event_id"]


def test_hubspot_webhook_accepted_without_signature_when_secret_unconfigured_in_dev(api_client, db):
    payload = {"eventId": "evt-dev", "subscriptionType": "x"}
    assert api_client.post("/api/commercial/webhooks/hubspot", json=payload).status_code == 200


def test_hubspot_webhook_rejected_without_signature_when_secret_unconfigured_outside_dev(
    api_client, db, monkeypatch
):
    from app.api.routes import webhooks as mod

    monkeypatch.setattr(
        mod, "get_settings",
        lambda: type("S", (), {"hubspot_webhook_secret": "", "app_env": "production"})(),
    )
    resp = api_client.post(
        "/api/commercial/webhooks/hubspot", json={"eventId": "evt-unconfigured", "subscriptionType": "x"}
    )
    assert resp.status_code == 503


def test_hubspot_webhook_invalid_signature_rejected_when_secret_configured(api_client, db, monkeypatch):
    from app.api.routes import webhooks as mod

    monkeypatch.setattr(
        mod, "get_settings",
        lambda: type("S", (), {"hubspot_webhook_secret": "sekret", "app_env": "development"})(),
    )
    resp = api_client.post(
        "/api/commercial/webhooks/hubspot",
        json={"eventId": "evt-bad", "subscriptionType": "x"},
        headers={"X-Hub-Signature": "wrong"},
    )
    assert resp.status_code == 401


def test_hubspot_webhook_valid_signature_accepted(api_client, db, monkeypatch):
    from app.api.routes import webhooks as mod

    secret = "sekret"
    monkeypatch.setattr(
        mod, "get_settings",
        lambda: type("S", (), {"hubspot_webhook_secret": secret, "app_env": "development"})(),
    )
    body = b'{"eventId": "evt-signed", "subscriptionType": "x"}'
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    resp = api_client.post(
        "/api/commercial/webhooks/hubspot",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature": signature},
    )
    assert resp.status_code == 200


def test_events_requires_internal_token(api_client, db):
    api_client.post(
        "/api/commercial/webhooks/hubspot", json={"eventId": "evt-2", "subscriptionType": "x"}
    )
    assert api_client.get("/api/commercial/events").status_code == 401
    resp = api_client.get("/api/commercial/events", headers=internal_headers())
    assert resp.status_code == 200
    assert len(resp.json()) >= 1
