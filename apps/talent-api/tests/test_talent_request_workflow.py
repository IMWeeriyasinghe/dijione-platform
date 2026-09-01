"""End-to-end talent request workflow: Customer Success review -> Talent
Acquisition stage progression, verifying Platform Core is sent the right
audit/notification calls at each step (AuditLog/Notification themselves are
platform-owned now — see ``platform_calls`` in conftest).

DijiTalentFlow is not a client intake portal (DijiTalentFlow real-data local
validation, 2026-09-01) — a client persona can no longer create a
TalentRequest via the API (see ``test_client_cannot_create_talent_request``
below). Test setup here seeds the request directly through
``TalentRequestService``, the same pattern ``test_tenant_isolation.py`` and
``test_client_scope_resolution.py`` already use.
"""

from app.schemas.talent_request import TalentRequestCreate
from app.services.talent_request_service import TalentRequestService


def _seed_request(db, *, client_id: int, created_by: int, designation: str, description: str = "d") -> dict:
    service = TalentRequestService(db)
    request = service.create_request(
        client_id=client_id, created_by=created_by,
        payload=TalentRequestCreate(designation=designation, description=description, required_skills=["x"]),
    )
    db.commit()
    return service.to_out(request).model_dump(mode="json")


def test_client_cannot_create_talent_request(api_client, two_tenant_world):
    """DijiTalentFlow is not a client intake portal — POST /api/talent/requests
    always 403s now, for every persona, since no role is granted
    talent.requests.create (see app/core/permissions.py in platform-api)."""
    resp = api_client.post(
        "/api/talent/requests",
        headers=two_tenant_world["abc_headers"],
        json={"designation": "Should Be Rejected", "description": "d", "required_skills": []},
    )
    assert resp.status_code == 403

    # Staff personas cannot reach it either — this is not merely a client
    # restriction, the creation capability is retired for everyone.
    resp = api_client.post(
        "/api/talent/requests",
        headers=two_tenant_world["ta_headers"],
        json={"designation": "Should Also Be Rejected", "description": "d", "required_skills": []},
    )
    assert resp.status_code == 403


def test_full_request_lifecycle(api_client, db, two_tenant_world, platform_calls):
    cs_headers = two_tenant_world["cs_headers"]
    ta_headers = two_tenant_world["ta_headers"]

    request = _seed_request(
        db, client_id=two_tenant_world["abc"].id, created_by=two_tenant_world["abc_user_id"],
        designation="Cloud Engineer", description="Own our cloud platform.",
    )
    assert request["customer_success_status"] == "PENDING_REVIEW"
    assert request["current_stage"] == "REQUEST_SUBMITTED"

    assert any(
        b["role"] == "CUSTOMER_SUCCESS" and b["type"] == "REQUEST_PENDING_REVIEW"
        for b in platform_calls["broadcasts"]
    )

    # A client persona cannot review its own request.
    client_headers = two_tenant_world["abc_headers"]
    forbidden = api_client.post(
        f"/api/talent/requests/{request['id']}/review",
        headers=client_headers,
        json={"decision": "APPROVED", "reason": "n/a"},
    )
    assert forbidden.status_code == 403

    review_resp = api_client.post(
        f"/api/talent/requests/{request['id']}/review",
        headers=cs_headers,
        json={"decision": "APPROVED", "reason": "Budget confirmed."},
    )
    assert review_resp.status_code == 200
    reviewed = review_resp.json()
    assert reviewed["customer_success_status"] == "APPROVED"
    assert reviewed["lifecycle_status"] == "APPROVED"

    stage_resp = api_client.post(
        f"/api/talent/requests/{request['id']}/stage",
        headers=ta_headers,
        json={"stage": "SOURCING"},
    )
    assert stage_resp.status_code == 200
    staged = stage_resp.json()
    assert staged["current_stage"] == "SOURCING"
    assert staged["progress_percent"] > 0

    assert any(
        b["role"] == "TALENT_CLIENT" and b["type"] == "APPLICATION_STAGE_CHANGED"
        for b in platform_calls["broadcasts"]
    )

    actions = {a["action"] for a in platform_calls["audit_events"] if a["entity_type"] == "TalentRequest"}
    assert {"talent_request.created", "talent_request.reviewed", "talent_request.stage_changed"} <= actions


def test_rejection_notifies_client_not_ta(api_client, db, two_tenant_world, platform_calls):
    cs_headers = two_tenant_world["cs_headers"]

    request = _seed_request(
        db, client_id=two_tenant_world["abc"].id, created_by=two_tenant_world["abc_user_id"],
        designation="Role To Reject",
    )

    review_resp = api_client.post(
        f"/api/talent/requests/{request['id']}/review",
        headers=cs_headers,
        json={"decision": "REJECTED", "reason": "Out of scope for this engagement."},
    )
    assert review_resp.status_code == 200
    assert review_resp.json()["lifecycle_status"] == "REJECTED"

    assert any(
        b["role"] == "TALENT_CLIENT" and b["type"] == "REQUEST_REJECTED"
        for b in platform_calls["broadcasts"]
    )
    assert not any(b["role"] == "TA_MEMBER" and b["type"] == "REQUEST_REJECTED" for b in platform_calls["broadcasts"])


def test_review_survives_platform_core_outage(api_client, db, two_tenant_world, monkeypatch):
    """CR §21/§27: a TalentFlow action must succeed even when Platform Core
    (audit/notifications) is genuinely unreachable — this test deliberately
    un-mocks the fixture and hits the real (unroutable) PLATFORM_API_URL.
    Exercises CS review (a still-client-relevant write path) rather than
    request creation, which is retired — see
    ``test_client_cannot_create_talent_request``."""
    request = _seed_request(
        db, client_id=two_tenant_world["abc"].id, created_by=two_tenant_world["abc_user_id"],
        designation="Resilience Check",
    )

    monkeypatch.undo()  # remove the autouse platform_calls patch for this test only

    resp = api_client.post(
        f"/api/talent/requests/{request['id']}/review",
        headers=two_tenant_world["cs_headers"],
        json={"decision": "APPROVED", "reason": "Resilience check."},
    )
    assert resp.status_code == 200
