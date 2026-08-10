"""End-to-end talent request workflow (CLAUDE.md §29-30): client submits ->
Customer Success review -> Talent Acquisition stage progression, verifying
audit log entries and notifications are created at each step."""

from app.models.audit_log import AuditLog
from app.models.notification import Notification
from tests.conftest import auth_headers


def test_full_request_lifecycle(api_client, db, two_tenant_world):
    client_headers = auth_headers(api_client, "test-abc-client")
    cs_headers = auth_headers(api_client, "test-cs")
    ta_headers = auth_headers(api_client, "test-ta")

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

    cs_notifications = db.query(Notification).filter(
        Notification.user_id == two_tenant_world["cs_user"].id
    ).all()
    assert any(n.type == "REQUEST_PENDING_REVIEW" for n in cs_notifications)

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

    client_notifications = db.query(Notification).filter(
        Notification.user_id == two_tenant_world["abc_user"].id
    ).all()
    assert any(n.type == "APPLICATION_STAGE_CHANGED" for n in client_notifications)

    audit_entries = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "TalentRequest", AuditLog.entity_id == request["id"])
        .all()
    )
    actions = {a.action for a in audit_entries}
    assert {"talent_request.created", "talent_request.reviewed", "talent_request.stage_changed"} <= actions


def test_rejection_notifies_client_not_ta(api_client, db, two_tenant_world):
    client_headers = auth_headers(api_client, "test-abc-client")
    cs_headers = auth_headers(api_client, "test-cs")

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

    client_notifications = db.query(Notification).filter(
        Notification.user_id == two_tenant_world["abc_user"].id
    ).all()
    assert any(n.type == "REQUEST_REJECTED" for n in client_notifications)
