"""Repeated HubSpot webhook delivery must not duplicate events. The Lever
webhook moved to recruitment-api with the Recruitment Source domain.
"""

from sqlalchemy import select

from app.models.integration_event import IntegrationEvent


def test_duplicate_hubspot_webhook_is_not_reprocessed(api_client, db):
    payload = {"eventId": "evt-hubspot-001", "subscriptionType": "company.propertyChange"}

    first = api_client.post("/api/talent/webhooks/hubspot", json=payload)
    assert first.status_code == 200
    second = api_client.post("/api/talent/webhooks/hubspot", json=payload)
    assert second.status_code == 200
    assert first.json()["event_id"] == second.json()["event_id"]
    assert second.json()["status"] == "IGNORED_DUPLICATE"

    events = list(
        db.execute(
            select(IntegrationEvent).where(
                IntegrationEvent.provider == "HUBSPOT",
                IntegrationEvent.external_event_id == "evt-hubspot-001",
            )
        ).scalars()
    )
    assert len(events) == 1
