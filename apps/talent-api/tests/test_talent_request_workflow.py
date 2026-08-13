"""End-to-end talent request workflow: client submits -> Customer Success
review -> Talent Acquisition stage progression, verifying Platform Core is
sent the right audit/notification calls at each step (AuditLog/Notification
themselves are platform-owned now — see ``platform_calls`` in conftest)."""


def test_full_request_lifecycle(api_client, db, two_tenant_world, platform_calls):
    client_headers = two_tenant_world["abc_headers"]
    cs_headers = two_tenant_world["cs_headers"]
    ta_headers = two_tenant_world["ta_headers"]

    create_resp = api_client.post(
        "/api/talent/requests",
        headers=client_headers,
        json={
            "designation": "Cloud Engineer",
            "description": "Own our cloud platform.",
            "required_skills": ["AWS", "Terraform"],
            "seniority": "Senior",
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    request = create_resp.json()
    assert request["customer_success_status"] == "PENDING_REVIEW"
    assert request["current_stage"] == "REQUEST_SUBMITTED"

    assert any(
        b["role"] == "CUSTOMER_SUCCESS" and b["type"] == "REQUEST_PENDING_REVIEW"
        for b in platform_calls["broadcasts"]
    )

    # A client persona cannot review its own request.
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
    client_headers = two_tenant_world["abc_headers"]
    cs_headers = two_tenant_world["cs_headers"]

    create_resp = api_client.post(
        "/api/talent/requests",
        headers=client_headers,
        json={"designation": "Role To Reject", "description": "d", "required_skills": []},
    )
    request_id = create_resp.json()["id"]

    review_resp = api_client.post(
        f"/api/talent/requests/{request_id}/review",
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


def test_talent_request_creation_survives_platform_core_outage(api_client, db, two_tenant_world, monkeypatch):
    """CR §21/§27: a TalentFlow action must succeed even when Platform Core
    (audit/notifications) is genuinely unreachable — this test deliberately
    un-mocks the fixture and hits the real (unroutable) PLATFORM_API_URL."""
    monkeypatch.undo()  # remove the autouse platform_calls patch for this test only

    resp = api_client.post(
        "/api/talent/requests",
        headers=two_tenant_world["abc_headers"],
        json={"designation": "Resilience Check", "description": "d", "required_skills": []},
    )
    assert resp.status_code == 201
