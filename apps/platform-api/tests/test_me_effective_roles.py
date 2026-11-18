"""D1: ``/api/auth/me`` must list the same module roles the token carries.
Frontends gate their application shells on it."""

from sqlalchemy import select

from app.core.security import decode_session_token
from app.models.access_group import AccessGroup, GroupModuleRole, UserGroupMembership
from app.models.user import User, UserModuleRole
from tests.conftest import ABC_CLIENT_ID, assign_client_scope, auth_headers

MODULE = "talent-flow"


def _without_permissions(entries):
    return [{k: v for k, v in e.items() if k != "permissions"} for e in entries]


def _me(api_client, headers):
    """The role entries (permissions are checked separately against the token)."""
    entries = api_client.get("/api/auth/me", headers=headers).json()["module_roles"]
    token = _token_modules(headers)
    for e in entries:
        assert e["permissions"] == token[e["module_key"]]["permissions"]  # same as the token carries
    return _without_permissions(entries)


def _token_modules(headers):
    return decode_session_token(headers["Authorization"].split()[1])["module_roles"]


def test_group_only_role_is_listed(api_client, db, two_tenant_world):
    user = User(email="group-only@example.com", full_name="Group Only", persona_key="test-group-only")
    group = AccessGroup(key="ta-team", display_name="TA Team")
    db.add_all([user, group])
    db.flush()
    db.add_all([
        UserGroupMembership(user_id=user.id, access_group_id=group.id),
        GroupModuleRole(access_group_id=group.id, module_key=MODULE, role="TA_MEMBER"),
    ])
    db.commit()

    headers = auth_headers(api_client, "test-group-only")
    assert _me(api_client, headers) == [{"module_key": MODULE, "role": "TA_MEMBER", "client_id": None, "enabled": True}]
    assert _token_modules(headers)[MODULE]["role"] == "TA_MEMBER"


def test_login_response_matches_me(api_client, db, two_tenant_world):
    role = db.execute(select(UserModuleRole).where(UserModuleRole.user_id == two_tenant_world["abc_user"].id)).scalars().one()
    assign_client_scope(db, role, client_id=ABC_CLIENT_ID)
    resp = api_client.post("/api/auth/dev-login", json={"persona_key": "test-abc-client"})
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    expected = [{"module_key": MODULE, "role": "TALENT_CLIENT", "client_id": ABC_CLIENT_ID, "enabled": True}]
    assert _without_permissions(resp.json()["user"]["module_roles"]) == expected
    assert _me(api_client, headers) == expected


def test_disabled_assignment_is_not_listed(api_client, db, two_tenant_world):
    admin = auth_headers(api_client, "test-platform-admin")
    ta_id = two_tenant_world["ta_user"].id
    assert api_client.put(
        f"/api/platform/admin/users/{ta_id}/modules/{MODULE}", json={"role": "TA_MEMBER", "enabled": False}, headers=admin
    ).status_code == 200

    headers = auth_headers(api_client, "test-ta")
    assert _me(api_client, headers) == []
    assert _token_modules(headers) == {}


def test_direct_role_wins_over_group_role_as_in_the_token(api_client, db, two_tenant_world):
    group = AccessGroup(key="managers", display_name="Managers")
    db.add(group)
    db.flush()
    db.add_all([
        UserGroupMembership(user_id=two_tenant_world["ta_user"].id, access_group_id=group.id),
        GroupModuleRole(access_group_id=group.id, module_key=MODULE, role="TA_MANAGER"),
    ])
    db.commit()

    headers = auth_headers(api_client, "test-ta")
    assert [r["role"] for r in _me(api_client, headers)] == ["TA_MEMBER"]
    assert _token_modules(headers)[MODULE]["role"] == "TA_MEMBER"
