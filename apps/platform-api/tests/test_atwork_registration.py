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
READ_OWN = "atwork.attendance.read_own"
RECORD_OWN = "atwork.attendance.record_own"
USER_PERMS = {ACCESS, READ_OWN, RECORD_OWN, "atwork.corrections.request_own"}
MANAGER_PERMS = USER_PERMS | {
    MANAGEMENT,
    "atwork.attendance.read",
    "atwork.corrections.review",
    "atwork.corrections.approve",
    "atwork.reports.read",
    "atwork.reports.export",
    "atwork.settings.manage",
    "atwork.audit.read",
}
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


def test_catalog_is_exact_and_scoped_to_the_module():
    assert {p.key for p in ATWORK_PERMISSIONS} == MANAGER_PERMS
    assert all(p.module_key == "atwork" for p in ATWORK_PERMISSIONS)
    roles = {r.key: set(r.permissions) for r in ATWORK_ROLES}
    assert roles == {"ATWORK_USER": USER_PERMS, "ATWORK_MANAGER": MANAGER_PERMS}
    assert all(r.module_key == "atwork" for r in ATWORK_ROLES)


def test_direct_roles_resolve_into_claims(api_client, db):
    for persona, role, expected in (("aw-user", "ATWORK_USER", USER_PERMS), ("aw-mgr", "ATWORK_MANAGER", MANAGER_PERMS)):
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
    assert set(_claims(api_client, "aw-group")["module_roles"]["atwork"]["permissions"]) == MANAGER_PERMS


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
    assert set(_claims(api_client, "test-ta")["module_roles"]["atwork"]["permissions"]) == MANAGER_PERMS


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
            "links": conn.execute(
                text("SELECT count(*) FROM role_permissions rp JOIN roles r ON r.id = rp.role_id WHERE r.module_key='atwork'")
            ).scalar(),
        }


def test_migration_single_head_idempotent_and_never_activates(tmp_path):
    url = f"sqlite:///{tmp_path / 'atwork-migration.db'}"
    heads = _alembic(url, "heads")
    assert heads.returncode == 0, heads.stderr
    assert heads.stdout.split() == ["o5p6q7r8s9t0", "(head)"]
    up = _alembic(url, "upgrade", "head")
    assert up.returncode == 0, up.stderr
    engine = create_engine(url)
    first = _snapshot(engine)
    assert len(first["module"]) == 1
    assert first["module"][0][0] == "COMING_SOON"
    assert not first["module"][0][2]
    assert (first["perms"], first["roles"], first["links"]) == (12, 2, 16)

    # An administrator's later status is preserved when the migration re-runs.
    with engine.begin() as conn:
        conn.execute(text("UPDATE application_modules SET enabled = 0 WHERE key='atwork'"))
    assert _alembic(url, "stamp", "m3n4o5p6q7r8").returncode == 0
    again = _alembic(url, "upgrade", "head")
    assert again.returncode == 0, again.stderr
    second = _snapshot(engine)
    assert not second["module"][0][1]
    assert (second["perms"], second["roles"], second["links"]) == (12, 2, 16)


def test_attendance_permissions_reach_existing_role_assignments(tmp_path):
    """A database already at atw1reg0b2c3 gains the links on its existing roles."""
    url = f"sqlite:///{tmp_path / 'atwork-existing.db'}"
    assert _alembic(url, "upgrade", "head").returncode == 0
    engine = create_engine(url)
    with engine.begin() as conn:
        ids = "SELECT id FROM permissions WHERE key LIKE 'atwork.attendance.%'"
        conn.execute(text(f"DELETE FROM role_permissions WHERE permission_id IN ({ids})"))
        conn.execute(text("DELETE FROM permissions WHERE key LIKE 'atwork.attendance.%'"))
    assert _alembic(url, "stamp", "atw1reg0b2c3").returncode == 0
    upgraded = _alembic(url, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr
    snapshot = _snapshot(engine)
    assert (snapshot["perms"], snapshot["roles"], snapshot["links"]) == (12, 2, 16)


def test_home_card_activates_in_dev_only_and_touches_only_atwork(tmp_path):
    for app_env, expected in (("uat", "COMING_SOON"), ("prod", "COMING_SOON"), ("development", "ACTIVE")):
        url = f"sqlite:///{tmp_path}/{app_env}.db"
        env = {**os.environ, "DATABASE_URL": url, "APP_ENV": app_env}
        env.pop("PYTHONPATH", None)

        def run(target, env=env):
            command = [sys.executable, "-m", "alembic", "upgrade", target]
            return subprocess.run(command, cwd=APP_ROOT, env=env, capture_output=True, text=True)

        assert run("n4o5p6q7r8s9").returncode == 0
        engine = create_engine(url)
        query = text("SELECT key, status FROM application_modules")
        grants = text("SELECT COUNT(*) FROM user_module_roles")
        with engine.connect() as conn:
            before, granted = dict(conn.execute(query).all()), conn.execute(grants).scalar()
        result = run("head")
        assert result.returncode == 0, result.stderr
        with engine.connect() as conn:
            after = dict(conn.execute(query).all())
            assert conn.execute(grants).scalar() == granted
        assert after["atwork"] == expected
        assert {k: v for k, v in after.items() if k != "atwork"} == {k: v for k, v in before.items() if k != "atwork"}
