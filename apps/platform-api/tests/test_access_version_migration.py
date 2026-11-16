"""Migration h4j6k8m0n2p3: users.access_version is additive, defaults to 0, reversible."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

APP_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS, THIS = "g3h5j7k9m1n2", "h4j6k8m0n2p3"


def _alembic(url, *args):
    env = {**os.environ, "DATABASE_URL": url, "APP_ENV": "production"}
    env.pop("PYTHONPATH", None)
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=APP_ROOT, env=env, capture_output=True, text=True)


def test_upgrade_adds_a_zero_default_column_and_changes_no_data(tmp_path):
    url = f"sqlite:///{tmp_path / 'av.db'}"
    assert _alembic(url, "upgrade", PREVIOUS).returncode == 0
    engine = create_engine(url)
    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO users (id, email, full_name, platform_role, is_active, identity_provider, internal_employee,"
            " created_at, updated_at) VALUES (1, 'a@example.com', 'A', 'PLATFORM_USER', 1, 'ENTRA', 0,"
            " CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ))
    up = _alembic(url, "upgrade", THIS)
    assert up.returncode == 0, up.stderr
    column = next(c for c in inspect(engine).get_columns("users") if c["name"] == "access_version")
    assert column["nullable"] is False
    with engine.connect() as c:
        assert c.execute(text("SELECT access_version FROM users WHERE id = 1")).scalar_one() == 0
    assert _alembic(url, "upgrade", THIS).returncode == 0  # re-run is a no-op


def test_downgrade_removes_only_the_column(tmp_path):
    url = f"sqlite:///{tmp_path / 'av_down.db'}"
    assert _alembic(url, "upgrade", THIS).returncode == 0
    down = _alembic(url, "downgrade", PREVIOUS)
    assert down.returncode == 0, down.stderr
    assert "access_version" not in {c["name"] for c in inspect(create_engine(url)).get_columns("users")}
    assert "email" in {c["name"] for c in inspect(create_engine(url)).get_columns("users")}
