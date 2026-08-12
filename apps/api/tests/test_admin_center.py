"""DijiOne Admin Center coverage (CR §34, §50, §53).

- PLATFORM_USER / TALENT_CLIENT / TA_MEMBER cannot reach admin APIs
- PLATFORM_ADMIN can manage ordinary users but not grant admin roles
- SUPER_ADMIN can manage administrators
- the last active SUPER_ADMIN can never be deactivated or demoted
- every mutation is audit-logged
"""

import pytest

from app.core.constants import MODULE_TALENT_FLOW, PlatformRole, TalentFlowRole
from app.models.user import User
from tests.conftest import auth_headers


@pytest.fixture()
def admin_world(db, two_tenant_world):
    platform_admin = User(
        email="platform-admin@example.com", full_name="Platform Admin",
        platform_role=PlatformRole.PLATFORM_ADMIN.value, persona_key="test-platform-admin",
    )
    super_admin = User(
        email="super-admin@example.com", full_name="Super Admin",
        platform_role=PlatformRole.SUPER_ADMIN.value, persona_key="test-super-admin",
    )
    db.add_all([platform_admin, super_admin])
    db.commit()
    return {**two_tenant_world, "platform_admin": platform_admin, "super_admin": super_admin}


def test_platform_user_cannot_access_admin(api_client, db, admin_world):
    headers = auth_headers(api_client, "test-abc-client")
    resp = api_client.get("/api/admin/dashboard", headers=headers)
    assert resp.status_code == 403


def test_ta_member_cannot_access_admin(api_client, db, admin_world):
    headers = auth_headers(api_client, "test-ta")
    resp = api_client.get("/api/admin/users", headers=headers)
    assert resp.status_code == 403


def test_platform_admin_can_access_admin_and_manage_users(api_client, db, admin_world):
    headers = auth_headers(api_client, "test-platform-admin")
    resp = api_client.get("/api/admin/dashboard", headers=headers)
    assert resp.status_code == 200

    resp = api_client.get("/api/admin/users", headers=headers)
    assert resp.status_code == 200
    target = next(u for u in resp.json() if u["email"] == "abc-user@example.com")

    resp = api_client.patch(
        f"/api/admin/users/{target['id']}/status", json={"is_active": False}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


def test_platform_admin_cannot_grant_super_admin(api_client, db, admin_world):
    headers = auth_headers(api_client, "test-platform-admin")
    users = api_client.get("/api/admin/users", headers=headers).json()
    target = next(u for u in users if u["email"] == "abc-user@example.com")

    resp = api_client.patch(
        f"/api/admin/users/{target['id']}/platform-role",
        json={"platform_role": "SUPER_ADMIN"},
        headers=headers,
    )
    assert resp.status_code == 403


def test_super_admin_can_manage_administrators(api_client, db, admin_world):
    headers = auth_headers(api_client, "test-super-admin")
    users = api_client.get("/api/admin/users", headers=headers).json()
    target = next(u for u in users if u["email"] == "abc-user@example.com")

    resp = api_client.patch(
        f"/api/admin/users/{target['id']}/platform-role",
        json={"platform_role": "PLATFORM_ADMIN"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["platform_role"] == "PLATFORM_ADMIN"


def test_last_super_admin_cannot_be_deactivated(api_client, db, admin_world):
    headers = auth_headers(api_client, "test-super-admin")
    users = api_client.get("/api/admin/users", headers=headers).json()
    self_record = next(u for u in users if u["email"] == "super-admin@example.com")

    resp = api_client.patch(
        f"/api/admin/users/{self_record['id']}/status", json={"is_active": False}, headers=headers
    )
    assert resp.status_code == 403


def test_last_super_admin_cannot_be_demoted(api_client, db, admin_world):
    headers = auth_headers(api_client, "test-super-admin")
    users = api_client.get("/api/admin/users", headers=headers).json()
    self_record = next(u for u in users if u["email"] == "super-admin@example.com")

    resp = api_client.patch(
        f"/api/admin/users/{self_record['id']}/platform-role",
        json={"platform_role": "PLATFORM_USER"},
        headers=headers,
    )
    assert resp.status_code == 403


def test_second_super_admin_allows_demotion_of_first(api_client, db, admin_world):
    second = User(
        email="super-admin-2@example.com", full_name="Second Super Admin",
        platform_role=PlatformRole.SUPER_ADMIN.value, persona_key="test-super-admin-2",
    )
    db.add(second)
    db.commit()

    headers = auth_headers(api_client, "test-super-admin-2")
    users = api_client.get("/api/admin/users", headers=headers).json()
    first = next(u for u in users if u["email"] == "super-admin@example.com")

    resp = api_client.patch(
        f"/api/admin/users/{first['id']}/platform-role",
        json={"platform_role": "PLATFORM_USER"},
        headers=headers,
    )
    assert resp.status_code == 200


def test_admin_mutations_are_audited(api_client, db, admin_world):
    headers = auth_headers(api_client, "test-platform-admin")
    users = api_client.get("/api/admin/users", headers=headers).json()
    target = next(u for u in users if u["email"] == "xyz-user@example.com")

    api_client.patch(f"/api/admin/users/{target['id']}/status", json={"is_active": False}, headers=headers)

    resp = api_client.get("/api/admin/audit", headers=auth_headers(api_client, "test-super-admin"))
    assert resp.status_code == 200
    actions = {e["action"] for e in resp.json()}
    assert "user.deactivated" in actions


def test_module_assignment_client_scope_via_admin_api(api_client, db, admin_world):
    headers = auth_headers(api_client, "test-platform-admin")
    users = api_client.get("/api/admin/users", headers=headers).json()
    ta = next(u for u in users if u["email"] == "ta-user@example.com")

    resp = api_client.put(
        f"/api/admin/users/{ta['id']}/modules/{MODULE_TALENT_FLOW}",
        json={
            "role": TalentFlowRole.TA_MEMBER.value,
            "enabled": True,
            "client_scope": {"all_clients": False, "client_ids": [admin_world["abc"].id]},
        },
        headers=headers,
    )
    assert resp.status_code == 200

    resp = api_client.get(f"/api/admin/users/{ta['id']}/effective-access", headers=headers)
    module = next(m for m in resp.json()["modules"] if m["module_key"] == MODULE_TALENT_FLOW)
    assert module["client_scope"]["all_clients"] is False
    assert module["client_scope"]["client_ids"] == [admin_world["abc"].id]

    # Enforcement follows immediately for the affected user.
    ta_headers = auth_headers(api_client, "test-ta")
    resp = api_client.get("/api/talent/clients", headers=ta_headers)
    names = {c["name"] for c in resp.json()}
    assert names == {"ABC Company"}
