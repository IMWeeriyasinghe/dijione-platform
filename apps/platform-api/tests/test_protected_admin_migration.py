"""Migration j6l8n0p2q4r5: the protected administrator policy and the initial SUPER_ADMIN grant."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

APP_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS, THIS = "i5k7m9n1p3q4", "j6l8n0p2q4r5"
EMAIL = "madushanka.weeriyasinghe@dijitalteam.com"
AUDIT_COUNT = "SELECT count(*) FROM audit_logs WHERE action = 'user.platform_role_changed' AND entity_id = 7"


def _alembic(url, *args):
    env = {**os.environ, "DATABASE_URL": url, "APP_ENV": "production"}
    env.pop("PYTHONPATH", None)
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=APP_ROOT, env=env, capture_output=True, text=True)


def _user(engine, uid, email, role="PLATFORM_ADMIN", oid=None):
    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO users (id, email, full_name, platform_role, is_active, identity_provider, internal_employee,"
            " entra_object_id, title, access_version, created_at, updated_at) VALUES (:i, :e, 'N', :r, 1, 'ENTRA', 1,"
            " :o, 'Architect', 3, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ), {"i": uid, "e": email, "r": role, "o": oid})


def test_existing_account_is_granted_the_role_and_nothing_else_changes(tmp_path):
    url = f"sqlite:///{tmp_path / 'p.db'}"
    assert _alembic(url, "upgrade", PREVIOUS).returncode == 0
    engine = create_engine(url)
    _user(engine, 7, EMAIL.upper(), oid="oid-7")
    _user(engine, 8, "other@example.com")
    up = _alembic(url, "upgrade", THIS)
    assert up.returncode == 0, up.stderr
    with engine.connect() as c:
        row = c.execute(text(
            "SELECT platform_role, entra_object_id, title, is_active, access_version FROM users WHERE id = 7"
        )).one()
        assert row[:4] == ("SUPER_ADMIN", "oid-7", "Architect", 1) and row[4] > 1_000_000_000
        other = c.execute(text("SELECT platform_role, access_version FROM users WHERE id = 8")).one()
        assert tuple(other) == ("PLATFORM_ADMIN", 3)
        assert c.execute(text("SELECT email, entra_object_id FROM protected_admins")).one() == (EMAIL, "oid-7")
        assert c.execute(text(AUDIT_COUNT)).scalar_one() == 1
    assert _alembic(url, "upgrade", THIS).returncode == 0  # re-run is safe
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM protected_admins")).scalar_one() == 1
        assert c.execute(text(AUDIT_COUNT)).scalar_one() == 1


def test_missing_account_registers_the_policy_and_creates_no_user(tmp_path):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    assert _alembic(url, "upgrade", THIS).returncode == 0
    with create_engine(url).connect() as c:
        assert c.execute(text("SELECT count(*) FROM protected_admins")).scalar_one() == 1
        assert c.execute(text("SELECT count(*) FROM users")).scalar_one() == 0
