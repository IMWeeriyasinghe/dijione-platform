"""Migration q8s0u2w4y6a8: additive tables and catalogue, idempotent, and a GUARDED downgrade that
refuses while appointments or suspensions exist (dropping a suspension would silently restore the
suspended people's group access)."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

APP_ROOT = Path(__file__).resolve().parents[1]
REVISION, PREVIOUS = "q8s0u2w4y6a8", "k7m9n1p3r5t7"


def _alembic(url, *args):
    env = {**os.environ, "DATABASE_URL": url, "APP_ENV": "production"}
    env.pop("PYTHONPATH", None)
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=APP_ROOT, env=env, capture_output=True, text=True)


def _catalog(engine):
    with engine.connect() as c:
        return (
            sorted(c.execute(text("SELECT key FROM permissions WHERE key LIKE '%.access.manage%'")).scalars()),
            sorted(c.execute(text("SELECT key FROM roles WHERE key LIKE '%_ACCESS_ADMIN' OR key LIKE '%_ACCESS_OWNER'"))
                   .scalars()),
            c.execute(text("SELECT COUNT(*) FROM role_permissions")).scalar(),
            c.execute(text("SELECT COUNT(*) FROM user_module_roles")).scalar(),
        )


def test_upgrade_is_additive_idempotent_and_downgrade_is_guarded(tmp_path):
    url = f"sqlite:///{(tmp_path / 'delegated.db').as_posix()}"
    assert _alembic(url, "upgrade", PREVIOUS).returncode == 0
    engine = create_engine(url)
    with engine.begin() as c:
        before_versions = c.execute(text("SELECT id, access_version FROM users ORDER BY id")).all()
    up = _alembic(url, "upgrade", "head")
    assert up.returncode == 0, up.stderr
    perms, roles, links, assignments = _catalog(engine)
    assert len(perms) == 8 and len(roles) == 8
    assert {"talent.access.manage", "atwork.access.manage_admins"} <= set(perms)
    with engine.begin() as c:
        assert c.execute(text("SELECT access_version FROM users ORDER BY id")).scalars().all() == [
            v for _i, v in before_versions
        ]  # nobody's session is revoked: no one's access changed

    # Re-running converges with no duplicates.
    assert _alembic(url, "downgrade", PREVIOUS).returncode == 0
    assert _alembic(url, "upgrade", "head").returncode == 0
    assert _catalog(engine) == (perms, roles, links, assignments)

    # With a suspension recorded, the downgrade refuses and changes nothing.
    with engine.begin() as c:
        c.execute(text("INSERT INTO users (email, full_name, platform_role, is_active, identity_provider, "
                       "internal_employee, access_version, created_at, updated_at) VALUES "
                       "('s@example.com', 'S', 'PLATFORM_USER', 1, 'ENTRA', 1, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
        uid = c.execute(text("SELECT id FROM users WHERE email = 's@example.com'")).scalar()
        c.execute(text("INSERT INTO application_access_suspensions (user_id, module_key, reason, created_at, updated_at) "
                       "VALUES (:u, 'talent-flow', 'left', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"), {"u": uid})
    refused = _alembic(url, "downgrade", PREVIOUS)
    assert refused.returncode != 0 and "silently restore" in refused.stderr
    with engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM application_access_suspensions")).scalar() == 1
        # Still at or after this revision: the refused downgrade did not pass it.
        assert c.execute(text("SELECT version_num FROM alembic_version")).scalar() != PREVIOUS

    # Once removed deliberately, the downgrade proceeds.
    with engine.begin() as c:
        c.execute(text("DELETE FROM application_access_suspensions"))
    assert _alembic(url, "downgrade", PREVIOUS).returncode == 0
    with engine.connect() as c:
        tables = {r[0] for r in c.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'"))}
    assert "application_access_suspensions" not in tables and "application_administrators" not in tables
    engine.dispose()


def test_birthday_registry_no_longer_claims_client_scope(tmp_path):
    """r9t1v3x5z7b9: registry metadata only; assignments and their client-scope rows are untouched."""
    url = f"sqlite:///{(tmp_path / 'birthday-scope.db').as_posix()}"
    assert _alembic(url, "upgrade", REVISION).returncode == 0
    engine = create_engine(url)

    def state():
        with engine.connect() as c:
            return (
                dict(c.execute(text("SELECT key, supports_client_scope FROM application_modules")).all()),
                c.execute(text("SELECT COUNT(*) FROM user_module_client_scopes")).scalar(),
                c.execute(text("SELECT COUNT(*) FROM user_module_roles")).scalar(),
            )

    caps, scopes, roles = state()
    if "birthday" not in caps:  # a database without the module registered: nothing to correct
        engine.dispose()
        return
    assert caps["birthday"] in (1, True)
    assert _alembic(url, "upgrade", "head").returncode == 0
    after, scopes_after, roles_after = state()
    assert after["birthday"] in (0, False)
    assert {k: v for k, v in after.items() if k != "birthday"} == {k: v for k, v in caps.items() if k != "birthday"}
    assert (scopes_after, roles_after) == (scopes, roles)
    assert _alembic(url, "upgrade", "head").returncode == 0  # idempotent
    assert _alembic(url, "downgrade", REVISION).returncode == 0
    assert state()[0]["birthday"] in (1, True)
    engine.dispose()
