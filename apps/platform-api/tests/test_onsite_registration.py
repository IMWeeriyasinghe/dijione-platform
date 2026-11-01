"""Diji On-site platform registration (PR 1.2): catalog, roles, claims,
module registry, and generic Admin discovery — registration data only.
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

from app.core.constants import MODULE_ONSITE
from app.core.permissions import (
    ALL_PERMISSIONS,
    ALL_ROLES,
    BIRTHDAY_PERMISSIONS,
    BIRTHDAY_ROLES,
    ONSITE_PERMISSIONS,
    ONSITE_ROLES,
    PLATFORM_PERMISSIONS,
    PLATFORM_ROLES,
    TALENT_PERMISSIONS,
    TALENT_ROLES,
)
from app.core.security import get_auth_provider
from app.models.module import ApplicationModule
from app.models.user import User, UserModuleRole
from tests.conftest import auth_headers

VIEWER = {"onsite.dashboard.read", "onsite.attendance.read", "onsite.exceptions.read"}
ADMIN = VIEWER | {"onsite.health.read", "onsite.identity.read", "onsite.sync.request", "onsite.sites.manage"}
APP_ROOT = Path(__file__).resolve().parents[1]


def _role(key):
    return next(r for r in ONSITE_ROLES if r.key == key)


def test_onsite_permission_catalog():
    assert MODULE_ONSITE == "onsite"
    assert {p.key for p in ONSITE_PERMISSIONS} == ADMIN
    assert all(p.module_key == "onsite" for p in ONSITE_PERMISSIONS)
    assert {p.key for p in ALL_PERMISSIONS} >= ADMIN


def test_onsite_roles_have_exact_permissions():
    assert {r.key for r in ONSITE_ROLES} == {"ONSITE_VIEWER", "ONSITE_ADMIN"}
    assert set(_role("ONSITE_VIEWER").permissions) == VIEWER
    assert set(_role("ONSITE_ADMIN").permissions) == ADMIN
    assert all(r.module_key == "onsite" for r in ONSITE_ROLES)


def test_other_modules_catalog_unchanged():
    # No other module's catalog gained or lost anything: On-site is appended.
    assert ALL_PERMISSIONS == PLATFORM_PERMISSIONS + TALENT_PERMISSIONS + BIRTHDAY_PERMISSIONS + ONSITE_PERMISSIONS
    assert ALL_ROLES == PLATFORM_ROLES + TALENT_ROLES + BIRTHDAY_ROLES + ONSITE_ROLES
    for defs in (PLATFORM_PERMISSIONS, TALENT_PERMISSIONS, BIRTHDAY_PERMISSIONS):
        assert not any(p.key.startswith("onsite.") or p.module_key == "onsite" for p in defs)
    for defs in (PLATFORM_ROLES, TALENT_ROLES, BIRTHDAY_ROLES):
        assert not any(r.module_key == "onsite" or any(k.startswith("onsite.") for k in r.permissions) for r in defs)
    assert {r.key for r in BIRTHDAY_ROLES} == {"BIRTHDAY_USER", "BIRTHDAY_ADMIN", "BIRTHDAY_SUPPLIER"}


def _onsite_user(db, role):
    user = User(email=f"{role.lower()}@example.com", full_name=f"{role} User",
                platform_role="PLATFORM_USER", persona_key=f"test-{role.lower()}")
    db.add(user)
    db.flush()
    db.add(UserModuleRole(user_id=user.id, module_key="onsite", role=role))
    db.commit()
    return user


def _claims(api_client, persona):
    token = api_client.post("/api/auth/dev-login", json={"persona_key": persona}).json()["access_token"]
    return get_auth_provider().decode_token(token)


def test_onsite_role_claims(api_client, db):
    _onsite_user(db, "ONSITE_ADMIN")
    _onsite_user(db, "ONSITE_VIEWER")

    admin = _claims(api_client, "test-onsite_admin")["module_roles"]["onsite"]
    assert admin["role"] == "ONSITE_ADMIN"
    assert set(admin["permissions"]) == ADMIN

    viewer = _claims(api_client, "test-onsite_viewer")["module_roles"]["onsite"]
    assert viewer["role"] == "ONSITE_VIEWER"
    assert set(viewer["permissions"]) == VIEWER


def _register_module(db):
    """Insert the exact registry row the data migration defines."""
    path = APP_ROOT / "alembic" / "versions" / "i9j0k1l2m3n4_register_onsite_module.py"
    spec = importlib.util.spec_from_file_location("onsite_registration_migration", path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    db.add(ApplicationModule(**mig.ONSITE_MODULE_ROW))
    db.commit()


def test_module_visible_only_to_onsite_role_holders(api_client, db, two_tenant_world):
    _register_module(db)
    _onsite_user(db, "ONSITE_VIEWER")

    keys = {m["key"] for m in api_client.get("/api/modules", headers=auth_headers(api_client, "test-onsite_viewer")).json()}
    assert "onsite" in keys
    keys = {m["key"] for m in api_client.get("/api/modules", headers=auth_headers(api_client, "test-ta")).json()}
    assert "onsite" not in keys


def test_admin_generic_discovery_and_assignment(api_client, db, two_tenant_world):
    _register_module(db)
    headers = auth_headers(api_client, "test-super-admin")

    modules = {m["key"]: m for m in api_client.get("/api/platform/admin/modules", headers=headers).json()}
    assert modules["onsite"]["status"] == "COMING_SOON"
    roles = {(r["module_key"], r["key"]) for r in api_client.get("/api/platform/admin/roles", headers=headers).json()}
    assert {("onsite", "ONSITE_VIEWER"), ("onsite", "ONSITE_ADMIN")} <= roles
    perms = {p["key"] for p in api_client.get("/api/platform/admin/permissions", headers=headers).json()}
    assert ADMIN <= perms

    target = two_tenant_world["ta_user"].id
    resp = api_client.put(f"/api/platform/admin/users/{target}/modules/onsite",
                          json={"role": "ONSITE_VIEWER"}, headers=headers)
    assert resp.status_code == 200, resp.text
    bad = api_client.put(f"/api/platform/admin/users/{target}/modules/onsite",
                         json={"role": "BIRTHDAY_ADMIN"}, headers=headers)
    assert bad.status_code in (400, 422)

    assert set(_claims(api_client, "test-ta")["module_roles"]["onsite"]["permissions"]) == VIEWER


def _onsite_without_client_scope(db):
    """Registry row as it stands after migration l2m3n4o5p6q7."""
    _register_module(db)
    db.query(ApplicationModule).filter_by(key="onsite").update({"supports_client_scope": False})
    db.commit()


def test_admin_center_lists_both_roles_and_no_client_scope(api_client, db, two_tenant_world):
    _onsite_without_client_scope(db)
    db.add(ApplicationModule(key="talent-flow", name="DijiTalentFlow", description="", route="/talent-flow"))
    db.commit()
    headers = auth_headers(api_client, "test-super-admin")
    roles = [r for r in api_client.get("/api/platform/admin/roles", headers=headers).json() if r["module_key"] == "onsite"]
    assert [(r["key"], r["name"]) for r in roles] == [("ONSITE_ADMIN", "On-site Admin"), ("ONSITE_VIEWER", "On-site Viewer")]
    modules = {m["key"]: m for m in api_client.get("/api/platform/admin/modules", headers=headers).json()}
    assert modules["onsite"]["supports_client_scope"] is False
    assert modules["talent-flow"]["supports_client_scope"] is True  # client-scoped modules unchanged
    detail = api_client.get("/api/platform/admin/applications/onsite", headers=headers).json()
    assert detail["supports_client_scope"] is False


def test_assign_viewer_then_admin_then_viewer_single_row(api_client, db, two_tenant_world):
    _onsite_without_client_scope(db)
    headers = auth_headers(api_client, "test-super-admin")
    target = two_tenant_world["ta_user"].id
    url = f"/api/platform/admin/users/{target}/modules/onsite"
    # A stray client scope (old UI) is ignored for a module that does not read it.
    stray = {"all_clients": False, "client_ids": [1]}
    for role, perms in (("ONSITE_VIEWER", VIEWER), ("ONSITE_ADMIN", ADMIN), ("ONSITE_VIEWER", VIEWER)):
        resp = api_client.put(url, json={"role": role, "enabled": True, "client_scope": stray}, headers=headers)
        assert resp.status_code == 200, resp.text
        db.expire_all()
        rows = db.query(UserModuleRole).filter_by(user_id=target, module_key="onsite").all()
        assert [(r.role, r.enabled) for r in rows] == [(role, True)]  # updated in place, never duplicated
        claim = _claims(api_client, "test-ta")["module_roles"]["onsite"]
        assert claim["role"] == role and set(claim["permissions"]) == perms
        assert claim["client_ids"] is None  # unrestricted; stray scope not stored
    detail = api_client.get("/api/platform/admin/applications/onsite", headers=headers).json()
    assert [(u["user_id"], u["role"], u["role_name"]) for u in detail["assigned_users"]] == [
        (target, "ONSITE_VIEWER", "On-site Viewer")]


def test_group_assignment_both_roles(api_client, db, two_tenant_world):
    from app.models.access_group import AccessGroup, GroupModuleRole

    _onsite_without_client_scope(db)
    group = AccessGroup(key="onsite-test-group", display_name="On-site test group")
    db.add(group)
    db.commit()
    headers = auth_headers(api_client, "test-super-admin")
    for role in ("ONSITE_VIEWER", "ONSITE_ADMIN"):
        resp = api_client.put(f"/api/platform/admin/groups/{group.id}/modules/onsite",
                              json={"role": role, "enabled": True, "client_scope": {"all_clients": False, "client_ids": [1]}},
                              headers=headers)
        assert resp.status_code == 200, resp.text
        db.expire_all()
        assert [r.role for r in db.query(GroupModuleRole).filter_by(access_group_id=group.id, module_key="onsite")] == [role]
    detail = api_client.get("/api/platform/admin/applications/onsite", headers=headers).json()
    assert [(g["role"], g["client_scope"]["all_clients"]) for g in detail["assigned_groups"]] == [("ONSITE_ADMIN", True)]


def _group_world(db, *, direct=None, group_role=None, group_enabled=True, group_status="ACTIVE"):
    from app.models.access_group import AccessGroup, GroupModuleRole, UserGroupMembership

    _register_module(db)
    user = User(email="grp@example.com", full_name="Group Member", platform_role="PLATFORM_USER", persona_key="test-grp")
    db.add(user)
    db.flush()
    if direct:
        db.add(UserModuleRole(user_id=user.id, module_key="onsite", role=direct))
    if group_role:
        group = AccessGroup(key="grp-onsite", display_name="Group", status=group_status)
        db.add(group)
        db.flush()
        db.add(UserGroupMembership(user_id=user.id, access_group_id=group.id))
        db.add(GroupModuleRole(access_group_id=group.id, module_key="onsite", role=group_role, enabled=group_enabled))
    db.commit()


def _home(api_client):
    return [m["key"] for m in api_client.get("/api/modules", headers=auth_headers(api_client, "test-grp")).json()]


def test_home_direct_only(api_client, db):
    _group_world(db, direct="ONSITE_VIEWER")
    assert _home(api_client).count("onsite") == 1


def test_home_group_only_viewer(api_client, db):
    _group_world(db, group_role="ONSITE_VIEWER")
    claim = _claims(api_client, "test-grp")["module_roles"]["onsite"]
    assert claim["role"] == "ONSITE_VIEWER" and set(claim["permissions"]) == VIEWER
    assert _home(api_client).count("onsite") == 1


def test_home_group_only_admin(api_client, db):
    _group_world(db, group_role="ONSITE_ADMIN")
    assert set(_claims(api_client, "test-grp")["module_roles"]["onsite"]["permissions"]) == ADMIN
    assert "onsite" in _home(api_client)


def test_home_disabled_group_assignment_hidden(api_client, db):
    _group_world(db, group_role="ONSITE_VIEWER", group_enabled=False)
    assert "onsite" not in _home(api_client)
    assert "onsite" not in _claims(api_client, "test-grp")["module_roles"]


def test_home_inactive_group_hidden(api_client, db):
    _group_world(db, group_role="ONSITE_ADMIN", group_status="INACTIVE")
    assert "onsite" not in _home(api_client)
    assert "onsite" not in _claims(api_client, "test-grp")["module_roles"]


def test_home_direct_plus_group_once_and_deterministic(api_client, db):
    _group_world(db, direct="ONSITE_VIEWER", group_role="ONSITE_ADMIN")
    assert _home(api_client).count("onsite") == 1
    claim = _claims(api_client, "test-grp")["module_roles"]["onsite"]
    assert claim["role"] == "ONSITE_VIEWER"  # direct grant is the primary role (existing claims rule)
    assert set(claim["permissions"]) == ADMIN  # permissions are the union across sources


def test_home_no_assignment_hidden(api_client, db):
    _group_world(db)
    assert "onsite" not in _home(api_client)


def _alembic(db_url, *args, app_env="development"):
    env = {**os.environ, "DATABASE_URL": db_url, "APP_ENV": app_env}
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=APP_ROOT, env=env,
                          capture_output=True, text=True)


def test_migration_fresh_db_registers_onsite_and_is_idempotent(tmp_path):
    url = f"sqlite:///{(tmp_path / 'mig.db').as_posix()}"
    up = _alembic(url, "upgrade", "head")
    assert up.returncode == 0, up.stderr
    assert "l2m3n4o5p6q7 (head)" in _alembic(url, "current").stdout

    eng = create_engine(url)

    def snapshot():
        with eng.connect() as c:
            return (
                c.execute(text("SELECT key,name,route,status,enabled,required_roles FROM application_modules"
                               " WHERE key='onsite'")).all(),
                sorted(c.execute(text("SELECT key FROM roles WHERE module_key='onsite'")).scalars()),
                sorted(c.execute(text("SELECT key FROM permissions WHERE module_key='onsite'")).scalars()),
                c.execute(text("SELECT COUNT(*) FROM role_permissions")).scalar(),
                sorted(c.execute(text("SELECT key FROM roles WHERE module_key IS NULL OR module_key!='onsite'")).scalars()),
            )

    first = snapshot()
    assert first[0] == [("onsite", "Diji On-site", "/onsite", "ACTIVE", 1, "ANY")]  # DEV (APP_ENV=development)
    assert first[1] == ["ONSITE_ADMIN", "ONSITE_VIEWER"]
    assert set(first[2]) == ADMIN
    with eng.connect() as c:
        caps = dict(c.execute(text("SELECT key, supports_client_scope FROM application_modules")).all())
    assert caps.pop("onsite") in (0, False) and all(v in (1, True) for v in caps.values())

    # Downgrade one step is a no-op data migration (repo convention); re-upgrade converges, no duplicates.
    assert _alembic(url, "downgrade", "-1").returncode == 0
    assert _alembic(url, "upgrade", "head").returncode == 0
    assert snapshot() == first
    eng.dispose()


def test_activation_is_dev_only(tmp_path):
    """UAT/PROD keep COMING_SOON; only APP_ENV=development activates it."""
    for app_env, expected in (("uat", "COMING_SOON"), ("prod", "COMING_SOON"), ("development", "ACTIVE")):
        url = f"sqlite:///{(tmp_path / f'{app_env}.db').as_posix()}"
        assert _alembic(url, "upgrade", "head", app_env=app_env).returncode == 0
        eng = create_engine(url)
        with eng.connect() as c:
            status = c.execute(text("SELECT status FROM application_modules WHERE key='onsite'")).scalar()
        eng.dispose()
        assert status == expected, app_env
