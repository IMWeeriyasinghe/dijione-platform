"""Webhook signature verification and duplicate-status hardening
(CLAUDE.md §60/§63) — production Lever webhooks are NOT being activated in
this phase, but the receiver must be ready: reject an invalid signature
when a secret is configured, accept when unconfigured (dev default), and
correctly mark repeated deliveries IGNORED_DUPLICATE rather than silently
re-returning the original untouched.
"""

import hashlib
import hmac

from sqlalchemy import select

from app.models.integration_event import IntegrationEvent


def _sign(secret: str, triggered_at: int) -> str:
    return hmac.new(
        secret.encode("utf-8"), f"{secret}{triggered_at}".encode(), hashlib.sha256
    ).hexdigest()


def test_webhook_accepted_without_signature_when_secret_unconfigured(api_client, db):
    # conftest.py never sets LEVER_WEBHOOK_SIGNING_SECRET, so the default
    # empty-string config applies here (dev posture: warn, don't reject).
    payload = {"id": "evt-nosig-1", "event": "candidateStageChange", "opportunityId": "opp-x", "stage": "Offer"}
    resp = api_client.post("/api/talent/webhooks/lever", json=payload)
    assert resp.status_code == 200


def test_invalid_signature_rejected_when_secret_configured(api_client, db, monkeypatch):
    from app.api.routes import webhooks as webhooks_module

    monkeypatch.setattr(
        webhooks_module, "get_settings",
        lambda: type("S", (), {"lever_webhook_signing_secret": "test-secret"})(),
    )
    payload = {
        "id": "evt-badsig-1", "event": "candidateStageChange", "opportunityId": "opp-x",
        "stage": "Offer", "triggeredAt": 1700000000000, "signature": "not-the-real-signature",
    }
    resp = api_client.post("/api/talent/webhooks/lever", json=payload)
    assert resp.status_code == 401

    events = list(
        db.execute(
            select(IntegrationEvent).where(IntegrationEvent.external_event_id == "evt-badsig-1")
        ).scalars()
    )
    assert len(events) == 0  # rejected before any event row is created


def test_valid_signature_accepted_when_secret_configured(api_client, db, monkeypatch):
    from app.api.routes import webhooks as webhooks_module

    secret = "test-secret"
    monkeypatch.setattr(
        webhooks_module, "get_settings",
        lambda: type("S", (), {"lever_webhook_signing_secret": secret})(),
    )
    triggered_at = 1700000000000
    payload = {
        "id": "evt-goodsig-1", "event": "candidateStageChange", "opportunityId": "opp-x",
        "stage": "Offer", "triggeredAt": triggered_at, "signature": _sign(secret, triggered_at),
    }
    resp = api_client.post("/api/talent/webhooks/lever", json=payload)
    assert resp.status_code == 200


def test_duplicate_delivery_marked_ignored_duplicate_not_reprocessed(api_client, db):
    payload = {"id": "evt-dup-1", "event": "candidateStageChange", "opportunityId": "opp-x", "stage": "Offer"}

    first = api_client.post("/api/talent/webhooks/lever", json=payload)
    assert first.status_code == 200
    assert first.json()["status"] == "PROCESSED"

    second = api_client.post("/api/talent/webhooks/lever", json=payload)
    assert second.status_code == 200
    assert second.json()["status"] == "IGNORED_DUPLICATE"
    assert second.json()["event_id"] == first.json()["event_id"]

    events = list(
        db.execute(
            select(IntegrationEvent).where(IntegrationEvent.external_event_id == "evt-dup-1")
        ).scalars()
    )
    assert len(events) == 1
