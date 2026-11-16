"""Migration k7m9n1p3r5t7: employee-record columns, LEGACY compatibility, always-on clean-up."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

APP_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS, THIS = "j6l8n0p2q4r5", "k7m9n1p3r5t7"
MODULE = "field-ops"  # any application with a default role; the migration is not module-specific


def _alembic(url, *args):
    env = {**os.environ, "DATABASE_URL": url, "APP_ENV": "production"}
    env.pop("PYTHONPATH", None)
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=APP_ROOT, env=env, capture_output=True, text=True)


def _user(c, uid, *, active=True, internal=True, oid="o"):
    c.execute(text(
        "INSERT INTO users (id, email, full_name, platform_role, is_active, identity_provider, internal_employee,"
        " entra_object_id, access_version, created_at, updated_at) VALUES (:i, :e, 'N', 'PLATFORM_USER', :a, 'ENTRA', :n,"
        " :o, 5, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    ), {"i": uid, "e": f"u{uid}@example.com", "a": active, "n": internal, "o": f"{oid}-{uid}" if oid else None})


def _role(c, rid, uid, module, role, enabled):
    c.execute(text(
        "INSERT INTO user_module_roles (id, user_id, module_key, role, enabled, created_at, updated_at)"
        " VALUES (:i, :u, :m, :r, :e, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    ), {"i": rid, "u": uid, "m": module, "r": role, "e": enabled})


def test_legacy_marking_and_exactly_the_opt_outs_are_removed(tmp_path):
    url = f"sqlite:///{tmp_path / 'd.db'}"
    assert _alembic(url, "upgrade", PREVIOUS).returncode == 0
    engine = create_engine(url)
    with engine.begin() as c:
        c.execute(text("DELETE FROM module_baseline_roles"))
        c.execute(text("INSERT INTO module_baseline_roles (module_key, role, enabled) VALUES (:m, :r, 1)"),
                  {"m": MODULE, "r": "FIELD_USER"})
        _user(c, 1)                          # eligible today -> LEGACY; opted out -> restored
        _user(c, 2, internal=False)          # not verified -> no LEGACY
        _user(c, 3, active=False)            # inactive -> no LEGACY
        _user(c, 4)                          # eligible, a talent assignment only
        _role(c, 10, 1, MODULE, "FIELD_USER", False)        # the opt-out
        _role(c, 11, 4, "talent-flow", "TA_MEMBER", False)  # an unrelated disabled assignment: kept
        _role(c, 12, 2, MODULE, "FIELD_MANAGER", True)      # a higher role: kept
        c.execute(text(
            "INSERT INTO user_module_client_scopes (user_module_role_id, all_clients, created_at, updated_at)"
            " VALUES (10, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ))
    up = _alembic(url, "upgrade", THIS)
    assert up.returncode == 0, up.stderr
    with engine.connect() as c:
        status = dict(c.execute(text("SELECT id, employee_record_status FROM users")).all())
        assert status == {1: "LEGACY", 2: None, 3: None, 4: "LEGACY"}
        assert sorted(r[0] for r in c.execute(text("SELECT id FROM user_module_roles"))) == [11, 12]
        assert c.execute(text("SELECT count(*) FROM user_module_client_scopes")).scalar_one() == 0
        audit = c.execute(text(
            "SELECT subject_user_id, event_metadata FROM audit_logs WHERE action = 'module_assignment.default_access_restored'"
        )).all()
        assert [a[0] for a in audit] == [1] and '"eligible": true' in audit[0][1]
        versions = dict(c.execute(text("SELECT id, access_version FROM users")).all())
        assert versions[1] > 1_000_000_000 and versions[4] == 5  # only the affected user is revoked
    assert _alembic(url, "upgrade", THIS).returncode == 0  # re-run is safe
    down = _alembic(url, "downgrade", PREVIOUS)
    assert down.returncode == 0, down.stderr
