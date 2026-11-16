"""D6 one assignment per user/group and application; D7 default employee
access can be removed and restored; D8 one person's access history."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.access_group import GroupModuleRole
from app.models.module import ApplicationModule
from app.models.module_baseline import ModuleBaselineRole
from app.models.role import Permission, Role, RolePermission
from app.models.user import User, UserModuleRole
from app.schemas.admin import ClientScopeIn
from app.services.admin_service import AdminService, ConflictError
from app.services.authorization_service import AuthorizationService
from app.services.claims_service import build_claims
from tests.conftest import auth_headers

ADMIN = "/api/platform/admin"
ALL_CLIENTS = {"all_clients": True, "client_ids": []}


@pytest.fixture()
def admin(api_client, two_tenant_world):
    return auth_headers(api_client, "test-platform-admin")


@pytest.fixture()
def employee(db, two_tenant_world):
    """An eligible internal employee with default Field Ops access and no assignment."""
    db.add_all([
        ApplicationModule(key="field-ops", name="Field Ops", description="", route="/field-ops", required_roles="ANY",
                          supports_client_scope=False),
        ModuleBaselineRole(module_key="field-ops", role="FIELD_USER", enabled=True),
    ])
    perm = Permission(key="field.manage", name="Manage", description="", module_key="field-ops", category="x")
    user_role = Role(module_key="field-ops", key="FIELD_USER", name="Field User", description="", is_system=False)
    manager_role = Role(module_key="field-ops", key="FIELD_MANAGER", name="Field Manager", description="", is_system=False)
    db.add_all([perm, user_role, manager_role])
    db.flush()
    db.add(RolePermission(role_id=manager_role.id, permission_id=perm.id))
    user = User(email="emp@example.com", full_name="Employee", persona_key="test-employee", internal_employee=True,
                identity_provider="ENTRA", entra_object_id="oid-emp", employee_record_status="MATCHED")
    db.add(user)
    db.commit()
    return user


# --- D6 ------------------------------------------------------------------------


def test_database_refuses_a_second_assignment_for_the_same_user_and_application(db, two_tenant_world):
    db.add(UserModuleRole(user_id=two_tenant_world["ta_user"].id, module_key="talent-flow", role="TA_MANAGER"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_database_refuses_a_second_assignment_for_the_same_group_and_application(api_client, db, admin):
    group_id = api_client.post(f"{ADMIN}/groups", json={"key": "g", "display_name": "G"}, headers=admin).json()["id"]
    db.add_all([
        GroupModuleRole(access_group_id=group_id, module_key="talent-flow", role="TA_MEMBER"),
        GroupModuleRole(access_group_id=group_id, module_key="talent-flow", role="TA_MANAGER"),
    ])
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_repeated_saves_update_the_one_row_and_a_revoke_removes_all_access(api_client, db, admin, two_tenant_world):
    user_id = two_tenant_world["ta_user"].id
    url = f"{ADMIN}/users/{user_id}/modules/talent-flow"
    for role in ("TA_MANAGER", "TA_MANAGER", "CUSTOMER_SUCCESS"):
        body = {"role": role, "enabled": True, "client_scope": ALL_CLIENTS}
        assert api_client.put(url, json=body, headers=admin).status_code == 200
    rows = db.execute(select(UserModuleRole).where(UserModuleRole.user_id == user_id)).scalars()
    assert [r.role for r in rows] == ["CUSTOMER_SUCCESS"]

    assert api_client.delete(url, headers=admin).status_code == 200
    db.expire_all()
    assert AuthorizationService(db).effective_module_roles(db.get(User, user_id)) == {}


def test_losing_a_race_to_create_an_assignment_is_a_conflict_not_a_second_row(db, two_tenant_world, monkeypatch):
    """Two requests both find no row and both insert. The second must fail cleanly."""
    actor_id, target_id = two_tenant_world["platform_admin"].id, two_tenant_world["ta_user"].id  # TA already assigned
    service = AdminService(db)
    monkeypatch.setattr(db, "execute", _stale_first_lookup(db))
    with pytest.raises(ConflictError):
        service.upsert_module_assignment(
            actor=db.get(User, actor_id), target_user_id=target_id, module_key="talent-flow", role="TA_MANAGER",
            enabled=True, client_scope=ClientScopeIn(all_clients=True),
        )
    monkeypatch.undo()
    rows = db.execute(select(UserModuleRole).where(UserModuleRole.user_id == target_id)).scalars().all()
    assert [r.role for r in rows] == ["TA_MEMBER"]


def _stale_first_lookup(db):
    """Make the service's "does a row exist?" query miss the other request's row once."""
    real, state = db.execute, {"missed": False}

    def execute(statement, *args, **kwargs):
        sql = str(statement)
        if not state["missed"] and "FROM user_module_roles" in sql and "user_module_roles.module_key =" in sql:
            state["missed"] = True
            return real(statement.where(UserModuleRole.id == -1), *args, **kwargs)
        return real(statement, *args, **kwargs)

    return execute


# --- D7 ------------------------------------------------------------------------


def test_default_access_is_always_on_and_cannot_be_removed(api_client, db, admin, employee):
    url = f"{ADMIN}/users/{employee.id}/modules/field-ops"
    assert list(build_claims(employee, db)["module_roles"]) == ["field-ops"]

    removed = api_client.delete(url, headers=admin)
    assert removed.status_code == 409, removed.text
    assert "cannot be removed" in removed.json()["detail"]
    db.expire_all()
    employee = db.get(User, employee.id)
    assert build_claims(employee, db)["module_roles"]["field-ops"]["role"] == "FIELD_USER"
    assert db.query(UserModuleRole).filter_by(user_id=employee.id).count() == 0
    effective = api_client.get(f"{ADMIN}/users/{employee.id}/effective-access", headers=admin).json()
    assert [m["module_key"] for m in effective["modules"]] == ["field-ops"] and effective["default_access_excluded"] == []

    # A disabled row of the default role (e.g. left over from before) no longer suppresses it.
    db.add(UserModuleRole(user_id=employee.id, module_key="field-ops", role="FIELD_USER", enabled=False))
    db.commit()
    assert build_claims(db.get(User, employee.id), db)["module_roles"]["field-ops"]["role"] == "FIELD_USER"
    # restore-default stays for compatibility: it clears the leftover row and is otherwise a no-op.
    assert api_client.post(f"{url}/restore-default", headers=admin).status_code == 200
    assert db.query(UserModuleRole).filter_by(user_id=employee.id).count() == 0
    assert api_client.post(f"{url}/restore-default", headers=admin).status_code == 200


def test_removing_a_direct_role_leaves_default_access_in_place(api_client, db, admin, employee):
    url = f"{ADMIN}/users/{employee.id}/modules/field-ops"
    assert api_client.put(url, json={"role": "FIELD_MANAGER", "enabled": True}, headers=admin).status_code == 200
    assert api_client.delete(url, headers=admin).status_code == 200
    db.expire_all()
    claim = build_claims(db.get(User, employee.id), db)["module_roles"]["field-ops"]
    assert claim["role"] == "FIELD_USER" and "field.manage" not in claim["permissions"]


def test_remove_is_still_not_found_when_there_is_nothing_to_remove(api_client, db, admin, employee, two_tenant_world):
    # A user who is not an eligible internal employee has no default access to remove.
    resp = api_client.delete(f"{ADMIN}/users/{two_tenant_world['ta_user'].id}/modules/field-ops", headers=admin)
    assert resp.status_code == 404
    assert db.query(UserModuleRole).filter_by(user_id=two_tenant_world["ta_user"].id, module_key="field-ops").count() == 0


def test_default_access_changes_need_manage_users(api_client, db, employee):
    headers = auth_headers(api_client, "test-ta")
    url = f"{ADMIN}/users/{employee.id}/modules/field-ops"
    assert api_client.delete(url, headers=headers).status_code == 403
    assert api_client.post(f"{url}/restore-default", headers=headers).status_code == 403


# --- D8 ------------------------------------------------------------------------


def test_user_audit_history_lists_everything_about_that_user_and_nobody_else(api_client, db, admin, employee, two_tenant_world):
    auditor = auth_headers(api_client, "test-super-admin")
    ta, cs = two_tenant_world["ta_user"], two_tenant_world["cs_user"]
    group_id = api_client.post(f"{ADMIN}/groups", json={"key": "g", "display_name": "G"}, headers=admin).json()["id"]

    api_client.patch(f"{ADMIN}/users/{ta.id}/status", json={"is_active": True}, headers=admin)
    api_client.put(f"{ADMIN}/users/{ta.id}/modules/talent-flow", json={"role": "TA_MANAGER", "enabled": True}, headers=admin)
    api_client.post(f"{ADMIN}/groups/{group_id}/members", json={"user_id": ta.id}, headers=admin)
    api_client.delete(f"{ADMIN}/groups/{group_id}/members/{ta.id}", headers=admin)
    api_client.delete(f"{ADMIN}/users/{ta.id}/modules/talent-flow", headers=admin)
    api_client.put(f"{ADMIN}/users/{employee.id}/modules/field-ops", json={"role": "FIELD_MANAGER", "enabled": True},
                   headers=admin)
    api_client.put(f"{ADMIN}/users/{cs.id}/modules/talent-flow", json={"role": "TA_MEMBER", "enabled": True}, headers=admin)

    def actions(user_id):
        resp = api_client.get(f"{ADMIN}/audit", params={"user_id": user_id}, headers=auditor)
        assert resp.status_code == 200
        return [e["action"] for e in reversed(resp.json())]

    assert actions(ta.id) == [
        "user.activated", "module_assignment.updated", "access_group.member_added", "access_group.member_removed",
        "module_assignment.removed",
    ]
    assert actions(employee.id) == ["module_assignment.created"]
    assert actions(cs.id) == ["module_assignment.updated"]

    everything = api_client.get(f"{ADMIN}/audit", headers=auditor).json()
    assert len(everything) > len(actions(ta.id))
    by_entity = api_client.get(f"{ADMIN}/audit", params={"entity_type": "User", "entity_id": ta.id}, headers=auditor).json()
    assert [e["action"] for e in by_entity] == ["user.activated"]


def test_user_audit_history_needs_view_audit(api_client, db, two_tenant_world):
    resp = api_client.get(f"{ADMIN}/audit", params={"user_id": 1}, headers=auth_headers(api_client, "test-ta"))
    assert resp.status_code == 403
