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


def _alembic(db_url, *args):
    env = {**os.environ, "DATABASE_URL": db_url}
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=APP_ROOT, env=env,
                          capture_output=True, text=True)


def test_migration_fresh_db_registers_onsite_and_is_idempotent(tmp_path):
    url = f"sqlite:///{(tmp_path / 'mig.db').as_posix()}"
    up = _alembic(url, "upgrade", "head")
    assert up.returncode == 0, up.stderr
    assert "i9j0k1l2m3n4" in _alembic(url, "current").stdout

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
    assert first[0] == [("onsite", "Diji On-site", "/onsite", "COMING_SOON", 1, "ANY")]
    assert first[1] == ["ONSITE_ADMIN", "ONSITE_VIEWER"]
    assert set(first[2]) == ADMIN

    # Downgrade one step is a no-op data migration (repo convention); re-upgrade converges, no duplicates.
    assert _alembic(url, "downgrade", "-1").returncode == 0
    assert _alembic(url, "upgrade", "head").returncode == 0
    assert snapshot() == first
    eng.dispose()
