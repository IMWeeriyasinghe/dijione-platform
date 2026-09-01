"""Lever webhook receiver: signature verification when configured, accepted
when unconfigured (dev), idempotent (duplicate -> IGNORED_DUPLICATE), and a
stage-change event updates only the local candidacy read model.
"""

import hashlib
import hmac

from sqlalchemy import select

from app.models.integration_event import IntegrationEvent
from app.models.posting import Posting
from app.models.recruitment_candidacy import RecruitmentCandidacy
from app.models.recruitment_candidate import RecruitmentCandidate


def _sign(secret: str, triggered_at: int) -> str:
    return hmac.new(secret.encode(), f"{secret}{triggered_at}".encode(), hashlib.sha256).hexdigest()


def test_accepted_without_signature_when_secret_unconfigured_in_dev(api_client, db):
    payload = {"id": "evt-1", "event": "candidateStageChange", "opportunityId": "opp-x", "stage": "Offer"}
    assert api_client.post("/api/recruitment/webhooks/lever", json=payload).status_code == 200


def test_rejected_without_signature_when_secret_unconfigured_outside_dev(api_client, db, monkeypatch):
    from app.api.routes import webhooks as mod

    monkeypatch.setattr(
        mod, "get_settings",
        lambda: type("S", (), {"lever_webhook_signing_secret": "", "app_env": "production"})(),
    )
    payload = {"id": "evt-unconfigured", "event": "x"}
    resp = api_client.post("/api/recruitment/webhooks/lever", json=payload)
    assert resp.status_code == 503
    assert not db.execute(
        select(IntegrationEvent).where(IntegrationEvent.external_event_id == "evt-unconfigured")
    ).scalars().all()


def test_invalid_signature_rejected_when_secret_configured(api_client, db, monkeypatch):
    from app.api.routes import webhooks as mod

    monkeypatch.setattr(
        mod, "get_settings",
        lambda: type("S", (), {"lever_webhook_signing_secret": "sekret", "app_env": "development"})(),
    )
    payload = {
        "id": "evt-bad", "event": "x", "triggeredAt": 1700000000000, "signature": "wrong",
    }
    resp = api_client.post("/api/recruitment/webhooks/lever", json=payload)
    assert resp.status_code == 401
    assert not db.execute(
        select(IntegrationEvent).where(IntegrationEvent.external_event_id == "evt-bad")
    ).scalars().all()


def test_valid_signature_accepted(api_client, db, monkeypatch):
    from app.api.routes import webhooks as mod

    secret, ts = "sekret", 1700000000000
    monkeypatch.setattr(
        mod, "get_settings",
        lambda: type("S", (), {"lever_webhook_signing_secret": secret, "app_env": "development"})(),
    )
    payload = {"id": "evt-ok", "event": "x", "triggeredAt": ts, "signature": _sign(secret, ts)}
    assert api_client.post("/api/recruitment/webhooks/lever", json=payload).status_code == 200


def test_duplicate_delivery_is_ignored(api_client, db):
    payload = {"id": "evt-dup", "event": "candidateStageChange", "opportunityId": "opp-x", "stage": "Offer"}
    first = api_client.post("/api/recruitment/webhooks/lever", json=payload)
    second = api_client.post("/api/recruitment/webhooks/lever", json=payload)
    assert first.json()["status"] == "PROCESSED"
    assert second.json()["status"] == "IGNORED_DUPLICATE"
    assert second.json()["event_id"] == first.json()["event_id"]
    assert len(db.execute(
        select(IntegrationEvent).where(IntegrationEvent.external_event_id == "evt-dup")
    ).scalars().all()) == 1


def test_stage_change_updates_local_candidacy(api_client, db):
    posting = Posting(lever_posting_id="post-1", title="Role")
    cand = RecruitmentCandidate(lever_contact_id="c-1", full_name="A", email="a@x.io")
    db.add_all([posting, cand])
    db.flush()
    db.add(RecruitmentCandidacy(
        recruitment_candidate_id=cand.id, posting_id=posting.id,
        lever_opportunity_id="opp-1", current_stage="SOURCING",
    ))
    db.commit()

    resp = api_client.post(
        "/api/recruitment/webhooks/lever",
        json={"id": "evt-stage", "event": "candidateStageChange", "opportunityId": "opp-1", "stage": "Offer"},
    )
    assert resp.json()["status"] == "PROCESSED"
    db.expire_all()
    row = db.execute(
        select(RecruitmentCandidacy).where(RecruitmentCandidacy.lever_opportunity_id == "opp-1")
    ).scalars().one()
    assert row.current_stage == "OFFER"
