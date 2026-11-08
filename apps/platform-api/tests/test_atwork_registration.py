"""DijiAtWork platform registration: catalog, claims, registry and migration."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

from app.core.permissions import ATWORK_PERMISSIONS, ATWORK_ROLES
from app.core.security import get_auth_provider
from app.models.access_group import AccessGroup, GroupModuleRole, UserGroupMembership
from app.models.module import ApplicationModule
from app.models.user import User, UserModuleRole
from tests.conftest import auth_headers

ACCESS = "atwork.access"
MANAGEMENT = "atwork.management.access"
APP_ROOT = Path(__file__).resolve().parents[1]
MIGRATION = APP_ROOT / "alembic" / "versions" / "atw1reg0b2c3_register_atwork_module.py"


def _migration():
    spec = importlib.util.spec_from_file_location("atwork_registration_migration", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _register_module(db):
    db.add(ApplicationModule(**_migration().ATWORK_MODULE_ROW))
    db.commit()


def _user(db, persona):
    user = User(email=f"{persona}@example.com", full_name=persona, platform_role="PLATFORM_USER", persona_key=persona)
    db.add(user)
    db.flush()
    return user


def _claims(api_client, persona):
    token = api_client.post("/api/auth/dev-login", json={"persona_key": persona}).json()["access_token"]
    return get_auth_provider().decode_token(token)


def test_catalog_is_minimal_and_scoped_to_the_module():
    assert {p.key for p in ATWORK_PERMISSIONS} == {ACCESS, MANAGEMENT}
    assert all(p.module_key == "atwork" for p in ATWORK_PERMISSIONS)
    roles = {r.key: set(r.permissions) for r in ATWORK_ROLES}
    assert roles == {"ATWORK_USER": {ACCESS}, "ATWORK_MANAGER": {ACCESS, MANAGEMENT}}
    assert all(r.module_key == "atwork" for r in ATWORK_ROLES)


def test_direct_roles_resolve_into_claims(api_client, db):
    for persona, role, expected in (("aw-user", "ATWORK_USER", {ACCESS}), ("aw-mgr", "ATWORK_MANAGER", {ACCESS, MANAGEMENT})):
        db.add(UserModuleRole(user_id=_user(db, persona).id, module_key="atwork", role=role))
        db.commit()
        claim = _claims(api_client, persona)["module_roles"]["atwork"]
        assert claim["role"] == role
        assert set(claim["permissions"]) == expected


def test_access_group_grant_resolves_through_effective_permissions(api_client, db):
    user = _user(db, "aw-group")
    group = AccessGroup(key="aw-test-group", display_name="AW group")
    db.add(group)
    db.flush()
    db.add(UserGroupMembership(user_id=user.id, access_group_id=group.id))
    db.add(GroupModuleRole(access_group_id=group.id, module_key="atwork", role="ATWORK_MANAGER", enabled=True))
    db.commit()
    assert set(_claims(api_client, "aw-group")["module_roles"]["atwork"]["permissions"]) == {ACCESS, MANAGEMENT}


def test_no_assignment_means_no_claim(api_client, db):
    _user(db, "aw-none")
    db.commit()
    assert "atwork" not in _claims(api_client, "aw-none")["module_roles"]


def test_module_visible_only_to_role_holders(api_client, db, two_tenant_world):
    _register_module(db)
    db.add(UserModuleRole(user_id=_user(db, "aw-visible").id, module_key="atwork", role="ATWORK_USER"))
    db.commit()
    modules = {m["key"]: m for m in api_client.get("/api/modules", headers=auth_headers(api_client, "aw-visible")).json()}
    assert modules["atwork"]["status"] == "COMING_SOON"
    other = {m["key"] for m in api_client.get("/api/modules", headers=auth_headers(api_client, "test-ta")).json()}
    assert "atwork" not in other


def test_admin_center_assigns_roles_without_client_scope(api_client, db, two_tenant_world):
    _register_module(db)
    headers = auth_headers(api_client, "test-super-admin")
    modules = {m["key"]: m for m in api_client.get("/api/platform/admin/modules", headers=headers).json()}
    assert modules["atwork"]["supports_client_scope"] is False
    url = f"/api/platform/admin/users/{two_tenant_world['ta_user'].id}/modules/atwork"
    assert api_client.put(url, json={"role": "ATWORK_MANAGER"}, headers=headers).status_code == 200
    assert api_client.put(url, json={"role": "BIRTHDAY_ADMIN"}, headers=headers).status_code in (400, 422)
    assert set(_claims(api_client, "test-ta")["module_roles"]["atwork"]["permissions"]) == {ACCESS, MANAGEMENT}


def _alembic(url, *args):
    env = {**os.environ, "DATABASE_URL": url, "APP_ENV": "production"}
    env.pop("PYTHONPATH", None)
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=APP_ROOT, env=env, capture_output=True, text=True)


def _snapshot(engine):
    with engine.connect() as conn:
        return {
            "module": conn.execute(
                text("SELECT status, enabled, supports_client_scope FROM application_modules WHERE key='atwork'")
            ).all(),
            "perms": conn.execute(text("SELECT count(*) FROM permissions WHERE module_key='atwork'")).scalar(),
            "roles": conn.execute(text("SELECT count(*) FROM roles WHERE module_key='atwork'")).scalar(),
            "links": conn.execute(text(
                "SELECT count(*) FROM role_permissions rp JOIN roles r ON r.id = rp.role_id WHERE r.module_key='atwork'"
            )).scalar(),
        }


def test_migration_single_head_idempotent_and_never_activates(tmp_path):
    url = f"sqlite:///{tmp_path / 'atwork-migration.db'}"
    heads = _alembic(url, "heads")
    assert heads.returncode == 0, heads.stderr
    assert heads.stdout.split() == ["atw1reg0b2c3", "(head)"]
    up = _alembic(url, "upgrade", "head")
    assert up.returncode == 0, up.stderr
    engine = create_engine(url)
    first = _snapshot(engine)
    assert len(first["module"]) == 1
    assert first["module"][0][0] == "COMING_SOON"
    assert not first["module"][0][2]
    assert (first["perms"], first["roles"], first["links"]) == (2, 2, 3)

    # An administrator's later status is preserved when the migration re-runs.
    with engine.begin() as conn:
        conn.execute(text("UPDATE application_modules SET enabled = 0 WHERE key='atwork'"))
    assert _alembic(url, "stamp", "m3n4o5p6q7r8").returncode == 0
    again = _alembic(url, "upgrade", "head")
    assert again.returncode == 0, again.stderr
    second = _snapshot(engine)
    assert not second["module"][0][1]
    assert (second["perms"], second["roles"], second["links"]) == (2, 2, 3)
