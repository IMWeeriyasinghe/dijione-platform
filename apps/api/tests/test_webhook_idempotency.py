"""Repeated webhook delivery must not duplicate domain records or events
(CLAUDE.md §64-65)."""

from app.models.integration_event import IntegrationEvent


def test_duplicate_lever_webhook_is_not_reprocessed(api_client, db):
    payload = {"id": "evt-lever-001", "event": "candidateStageChange", "opportunityId": "opp-x", "stage": "Offer"}

    first = api_client.post("/api/webhooks/lever", json=payload)
    assert first.status_code == 200
    second = api_client.post("/api/webhooks/lever", json=payload)
    assert second.status_code == 200
    assert first.json()["event_id"] == second.json()["event_id"]

    events = (
        db.query(IntegrationEvent)
        .filter(IntegrationEvent.provider == "LEVER", IntegrationEvent.external_event_id == "evt-lever-001")
        .all()
    )
    assert len(events) == 1


def test_duplicate_hubspot_webhook_is_not_reprocessed(api_client, db):
    payload = {"eventId": "evt-hubspot-001", "subscriptionType": "company.propertyChange"}

    first = api_client.post("/api/webhooks/hubspot", json=payload)
    assert first.status_code == 200
    second = api_client.post("/api/webhooks/hubspot", json=payload)
    assert second.status_code == 200
    assert first.json()["event_id"] == second.json()["event_id"]

    events = (
        db.query(IntegrationEvent)
        .filter(IntegrationEvent.provider == "HUBSPOT", IntegrationEvent.external_event_id == "evt-hubspot-001")
        .all()
    )
    assert len(events) == 1


def test_lever_stage_sync_updates_linked_application(api_client, db, two_tenant_world):
    from app.models.external_mapping import ExternalMapping
    from app.schemas.application import ApplicationCreate
    from app.schemas.candidate import CandidateCreate
    from app.schemas.talent_request import TalentRequestCreate
    from app.services.application_service import ApplicationService
    from app.services.candidate_service import CandidateService
    from app.services.talent_request_service import TalentRequestService

    request_service = TalentRequestService(db)
    request = request_service.create_request(
        client_id=two_tenant_world["abc"].id, created_by=two_tenant_world["abc_user"].id,
        payload=TalentRequestCreate(designation="Role", description="d", required_skills=[]),
    )
    candidate_service = CandidateService(db)
    candidate = candidate_service.create_candidate(
        CandidateCreate(full_name="Test Candidate", email="test-candidate@example.com")
    )
    application_service = ApplicationService(db)
    application = application_service.create_application(
        actor_id=two_tenant_world["ta_user"].id,
        payload=ApplicationCreate(candidate_id=candidate.id, talent_request_id=request.id),
    )
    db.add(
        ExternalMapping(
            provider="LEVER", external_object_type="opportunity", external_id="opp-sync-test",
            internal_object_type="Application", internal_id=application.id,
        )
    )
    db.commit()

    resp = api_client.post(
        "/api/webhooks/lever",
        json={
            "id": "evt-sync-1", "event": "candidateStageChange",
            "opportunityId": "opp-sync-test", "stage": "Offer",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "PROCESSED"

    db.refresh(application)
    assert application.current_stage == "OFFER"
