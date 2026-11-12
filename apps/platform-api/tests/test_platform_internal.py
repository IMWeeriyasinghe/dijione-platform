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


DELIVER = "/api/platform/internal/notifications/deliver"


def _deliver(api_client, **body):
    payload = {"dedupe_key": "k1", "type": "T", "title": "Title", "body": "Body", "link_url": "/somewhere/1", **body}
    return api_client.post(DELIVER, json=payload, headers=internal_headers())


def test_deliver_requires_the_internal_secret(api_client, db):
    assert api_client.post(DELIVER, json={}).status_code == 401


def test_deliver_is_idempotent_and_returns_the_link(api_client, db, two_tenant_world):
    user = two_tenant_world["abc_user"]
    assert _deliver(api_client, user_id=user.id).json()["created"] == 1
    assert _deliver(api_client, user_id=user.id).json()["created"] == 0
    from app.models.notification import Notification

    rows = db.query(Notification).filter_by(user_id=user.id, dedupe_key="k1").all()
    assert len(rows) == 1 and rows[0].link_url == "/somewhere/1"


def test_deliver_rejects_external_links_and_ambiguous_targets(api_client, db, two_tenant_world):
    user_id = two_tenant_world["abc_user"].id
    assert _deliver(api_client, user_id=user_id, link_url="https://evil.example").status_code == 422
    assert _deliver(api_client, user_id=user_id, link_url="//evil.example").status_code == 422
    assert _deliver(api_client).status_code == 422


def test_deliver_uses_effective_permissions_and_exclusions(api_client, db, two_tenant_world):
    from app.models.notification import Notification
    from app.models.user import UserModuleRole
    from app.services.authorization_service import AuthorizationService

    ta = two_tenant_world["ta_user"]
    permissions = sorted(AuthorizationService(db).effective_permissions(ta, "talent-flow"))
    assert permissions
    module = {"module_key": "talent-flow", "required_permissions": permissions[:1]}
    holders = db.query(UserModuleRole.user_id).filter_by(module_key="talent-flow").all()
    assert len(holders) >= 1

    out = _deliver(api_client, dedupe_key="perm", **module).json()
    assert out["created"] == out["recipients"] >= 1
    assert db.query(Notification).filter_by(user_id=ta.id, dedupe_key="perm").count() == 1

    _deliver(api_client, dedupe_key="excl", exclude_user_ids=[ta.id], **module)
    assert db.query(Notification).filter_by(user_id=ta.id, dedupe_key="excl").count() == 0

    none = _deliver(api_client, dedupe_key="no", module_key="talent-flow", required_permissions=["not.a.permission"]).json()
    assert none == {"status": "ok", "recipients": 0, "created": 0}


def test_notifications_stay_private_to_their_recipient(api_client, db, two_tenant_world):
    _deliver(api_client, user_id=two_tenant_world["abc_user"].id, dedupe_key="secret", title="Only for ABC")
    other = api_client.get("/api/notifications", headers=auth_headers(api_client, "test-ta")).json()
    assert all(n["title"] != "Only for ABC" for n in other)
