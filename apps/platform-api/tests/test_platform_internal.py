"""Service-to-service write surface used by talent-api (audit events,
notifications) — CR §27, §48. Never reachable without the internal secret,
even for an otherwise-authenticated user."""

from tests.conftest import auth_headers, internal_headers


def test_internal_endpoints_reject_missing_token(api_client, db):
    resp = api_client.post(
        "/api/platform/internal/audit-events",
        json={"action": "x", "entity_type": "Y", "entity_id": 1},
    )
    assert resp.status_code == 401


def test_internal_endpoints_reject_a_user_bearer_token(api_client, db, two_tenant_world):
    headers = auth_headers(api_client, "test-ta")
    resp = api_client.post(
        "/api/platform/internal/audit-events",
        json={"action": "x", "entity_type": "Y", "entity_id": 1},
        headers=headers,
    )
    assert resp.status_code == 401


def test_create_audit_event(api_client, db, two_tenant_world):
    resp = api_client.post(
        "/api/platform/internal/audit-events",
        json={
            "actor_id": two_tenant_world["ta_user"].id,
            "action": "talent_request.created",
            "entity_type": "TalentRequest",
            "entity_id": 42,
        },
        headers=internal_headers(),
    )
    assert resp.status_code == 201

    resp = api_client.get(
        "/api/platform/admin/audit", headers=auth_headers(api_client, "test-super-admin")
    )
    actions = {e["action"] for e in resp.json()}
    assert "talent_request.created" in actions


def test_create_notification(api_client, db, two_tenant_world):
    resp = api_client.post(
        "/api/platform/internal/notifications",
        json={
            "user_id": two_tenant_world["abc_user"].id,
            "type": "REQUEST_APPROVED",
            "title": "Your request was approved",
        },
        headers=internal_headers(),
    )
    assert resp.status_code == 201

    resp = api_client.get(
        "/api/notifications", headers=auth_headers(api_client, "test-abc-client")
    )
    assert any(n["title"] == "Your request was approved" for n in resp.json())


def test_broadcast_notification_to_module_role_holders(api_client, db, two_tenant_world):
    resp = api_client.post(
        "/api/platform/internal/notifications/broadcast",
        json={
            "module_key": "talent-flow",
            "role": "CUSTOMER_SUCCESS",
            "type": "REQUEST_PENDING_REVIEW",
            "title": "New request needs review",
        },
        headers=internal_headers(),
    )
    assert resp.status_code == 201

    resp = api_client.get(
        "/api/notifications", headers=auth_headers(api_client, "test-cs")
    )
    assert any(n["title"] == "New request needs review" for n in resp.json())


def test_module_role_holders(api_client, db, two_tenant_world):
    resp = api_client.get(
        "/api/platform/internal/module-roles/talent-flow/CUSTOMER_SUCCESS/user-ids",
        headers=internal_headers(),
    )
    assert resp.status_code == 200
    assert two_tenant_world["cs_user"].id in resp.json()["user_ids"]
