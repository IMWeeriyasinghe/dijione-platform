"""D5: a scope that names no client must never be stored, because an
assignment with no scope rows resolves as unrestricted (ALL_CLIENTS)."""

import pytest
from sqlalchemy import select

from app.models.access_group import GroupModuleRole
from app.models.user import User, UserModuleRole
from app.services.authorization_service import AuthorizationService
from tests.conftest import ABC_CLIENT_ID, auth_headers

MODULE = "talent-flow"
EMPTY_SPECIFIC = {"all_clients": False, "client_ids": []}
ALL_CLIENTS = {"all_clients": True, "client_ids": []}


@pytest.fixture()
def admin(api_client, two_tenant_world):
    return auth_headers(api_client, "test-platform-admin")


@pytest.fixture()
def newcomer(db, two_tenant_world):
    user = User(email="newcomer@example.com", full_name="Newcomer", persona_key="test-newcomer")
    db.add(user)
    db.commit()
    return user


def _user_url(user_id):
    return f"/api/platform/admin/users/{user_id}/modules/{MODULE}"


def _new_group(api_client, admin):
    resp = api_client.post("/api/platform/admin/groups", json={"key": "d5", "display_name": "D5"}, headers=admin)
    return resp.json()["id"]


def test_new_user_assignment_with_empty_specific_scope_is_rejected(api_client, db, admin, newcomer):
    resp = api_client.put(
        _user_url(newcomer.id), json={"role": "TA_MEMBER", "enabled": True, "client_scope": EMPTY_SPECIFIC}, headers=admin
    )
    assert resp.status_code == 400
    assert "at least one client" in resp.json()["detail"]
    assert db.execute(select(UserModuleRole).where(UserModuleRole.user_id == newcomer.id)).first() is None


def test_new_user_assignment_without_scope_is_rejected(api_client, db, admin, newcomer):
    resp = api_client.put(_user_url(newcomer.id), json={"role": "TA_MEMBER", "enabled": True}, headers=admin)
    assert resp.status_code == 400
    assert "Client scope is required" in resp.json()["detail"]
    assert db.execute(select(UserModuleRole).where(UserModuleRole.user_id == newcomer.id)).first() is None


def test_restricted_user_cannot_be_widened_by_an_empty_scope(api_client, db, admin, newcomer):
    restricted = {"all_clients": False, "client_ids": [ABC_CLIENT_ID]}
    assert api_client.put(
        _user_url(newcomer.id), json={"role": "TA_MEMBER", "enabled": True, "client_scope": restricted}, headers=admin
    ).status_code == 200

    resp = api_client.put(
        _user_url(newcomer.id), json={"role": "TA_MEMBER", "enabled": True, "client_scope": EMPTY_SPECIFIC}, headers=admin
    )
    assert resp.status_code == 400

    db.expire_all()
    scope, _sources = AuthorizationService(db).effective_client_scope(db.get(User, newcomer.id), MODULE)
    assert scope == [ABC_CLIENT_ID]


def test_existing_assignment_keeps_its_scope_when_none_is_sent(api_client, db, admin, newcomer):
    restricted = {"all_clients": False, "client_ids": [ABC_CLIENT_ID]}
    api_client.put(_user_url(newcomer.id), json={"role": "TA_MEMBER", "enabled": True, "client_scope": restricted}, headers=admin)

    resp = api_client.put(_user_url(newcomer.id), json={"role": "TA_MANAGER", "enabled": True}, headers=admin)
    assert resp.status_code == 200
    assignment = resp.json()["module_assignments"][0]
    assert assignment["role"] == "TA_MANAGER"
    assert assignment["client_scope"] == {"all_clients": False, "client_ids": [ABC_CLIENT_ID], "client_names": ["ABC Company"]}


def test_explicit_all_clients_is_still_accepted(api_client, admin, newcomer):
    resp = api_client.put(
        _user_url(newcomer.id), json={"role": "TA_MEMBER", "enabled": True, "client_scope": ALL_CLIENTS}, headers=admin
    )
    assert resp.status_code == 200
    assert resp.json()["module_assignments"][0]["client_scope"]["all_clients"] is True


@pytest.mark.parametrize("scope", [EMPTY_SPECIFIC, None])
def test_new_group_assignment_needs_an_explicit_scope(api_client, db, admin, scope):
    group_id = _new_group(api_client, admin)
    resp = api_client.put(
        f"/api/platform/admin/groups/{group_id}/modules/{MODULE}",
        json={"role": "TA_MEMBER", "enabled": True, "client_scope": scope},
        headers=admin,
    )
    assert resp.status_code == 400
    assert db.execute(select(GroupModuleRole).where(GroupModuleRole.access_group_id == group_id)).first() is None
