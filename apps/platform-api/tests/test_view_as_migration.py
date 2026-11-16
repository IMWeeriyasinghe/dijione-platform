"""Migration i5k7m9n1p3q4: View-as sessions table and permission, SUPER_ADMIN only."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

APP_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS, THIS = "h4j6k8m0n2p3", "i5k7m9n1p3q4"


def _alembic(url, *args):
    env = {**os.environ, "DATABASE_URL": url, "APP_ENV": "production"}
    env.pop("PYTHONPATH", None)
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=APP_ROOT, env=env, capture_output=True, text=True)


def _seed_roles(engine):
    with engine.begin() as c:
        for key in ("SUPER_ADMIN", "PLATFORM_ADMIN"):
            if c.execute(text("SELECT 1 FROM roles WHERE key = :k AND module_key IS NULL"), {"k": key}).first() is None:
                c.execute(text(
                    "INSERT INTO roles (key, name, description, module_key, is_system, created_at, updated_at) "
                    "VALUES (:k, :k, '', NULL, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ), {"k": key})
        c.execute(text(
            "INSERT INTO users (id, email, full_name, platform_role, is_active, identity_provider, internal_employee,"
            " created_at, updated_at) VALUES (1, 'a@example.com', 'A', 'PLATFORM_USER', 1, 'ENTRA', 0,"
            " CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ))


def test_upgrade_creates_the_table_links_the_permission_to_super_admin_only_and_raises_versions(tmp_path):
    url = f"sqlite:///{tmp_path / 'va.db'}"
    assert _alembic(url, "upgrade", PREVIOUS).returncode == 0
    engine = create_engine(url)
    _seed_roles(engine)
    up = _alembic(url, "upgrade", THIS)
    assert up.returncode == 0, up.stderr
    assert "view_as_sessions" in inspect(engine).get_table_names()
    with engine.connect() as c:
        holders = {r[0] for r in c.execute(text(
            "SELECT r.key FROM role_permissions rp JOIN roles r ON r.id = rp.role_id "
            "JOIN permissions p ON p.id = rp.permission_id WHERE p.key = 'platform.admin.view_as'"
        ))}
        assert holders == {"SUPER_ADMIN"}
        assert c.execute(text("SELECT access_version FROM users WHERE id = 1")).scalar_one() > 1_000_000_000  # raised
    assert _alembic(url, "upgrade", THIS).returncode == 0  # safe to re-run


def test_downgrade_drops_only_the_table(tmp_path):
    url = f"sqlite:///{tmp_path / 'va_down.db'}"
    assert _alembic(url, "upgrade", THIS).returncode == 0
    down = _alembic(url, "downgrade", PREVIOUS)
    assert down.returncode == 0, down.stderr
    assert "view_as_sessions" not in inspect(create_engine(url)).get_table_names()
