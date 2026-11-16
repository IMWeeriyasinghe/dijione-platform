"""Migration g3h5j7k9m1n2: unique access assignments and the audit subject."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

APP_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS, THIS = "f2a4b6c8d0e2", "g3h5j7k9m1n2"


def _alembic(url, *args):
    env = {**os.environ, "DATABASE_URL": url, "APP_ENV": "production"}
    env.pop("PYTHONPATH", None)
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=APP_ROOT, env=env, capture_output=True, text=True)


@pytest.fixture()
def at_previous(tmp_path):
    url = f"sqlite:///{tmp_path / 'integrity.db'}"
    up = _alembic(url, "upgrade", PREVIOUS)
    assert up.returncode == 0, up.stderr
    engine = create_engine(url)
    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO users (id, email, full_name, platform_role, is_active, identity_provider, internal_employee,"
            " created_at, updated_at) VALUES (1, 'a@example.com', 'A', 'PLATFORM_USER', 1, 'ENTRA', 0,"
            " CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), (2, 'b@example.com', 'B', 'PLATFORM_USER', 1, 'ENTRA', 0,"
            " CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ))
    yield url, engine
    engine.dispose()


def _assignment(conn, user_id, role="TA_MEMBER"):
    conn.execute(text(
        "INSERT INTO user_module_roles (user_id, module_key, role, enabled, created_at, updated_at)"
        " VALUES (:u, 'talent-flow', :r, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    ), {"u": user_id, "r": role})


def _audit(conn, entity_type, entity_id, previous_state="", new_state=""):
    conn.execute(text(
        "INSERT INTO audit_logs (action, entity_type, entity_id, previous_state, new_state, event_metadata, created_at)"
        " VALUES ('x', :t, :e, :p, :n, '', CURRENT_TIMESTAMP)"
    ), {"t": entity_type, "e": entity_id, "p": previous_state, "n": new_state})


def test_single_head_and_upgrade_adds_constraints_and_backfills_subjects(at_previous):
    url, engine = at_previous
    heads = _alembic(url, "heads")
    assert len(heads.stdout.split()) == 2 and heads.stdout.split()[1] == "(head)", heads.stdout  # one head, whatever follows THIS

    with engine.begin() as c:
        _assignment(c, 1)
        _audit(c, "User", 2, new_state='{"is_active": false}')
        _audit(c, "UserModuleRole", 50, new_state='{"user_id": 1, "module_key": "talent-flow", "role": "TA_MEMBER"}')
        _audit(c, "UserGroupMembership", 60, previous_state='{"user_id": 2, "access_group_id": 9}')
        _audit(c, "UserModuleRole", 51, previous_state='{"module_key": "talent-flow", "role": "TA_MEMBER"}')  # no user recorded
        _audit(c, "UserModuleRole", 52, new_state='{"user_id": 999}')  # user no longer exists
        _audit(c, "TalentRequest", 1, new_state='{"user_id": 1}')  # another service's event
        _audit(c, "UserModuleRole", 53, new_state="not json")
    content = text("SELECT id, action, entity_type, entity_id, previous_state, new_state FROM audit_logs ORDER BY id")
    with engine.connect() as c:
        before = c.execute(content).all()

    up = _alembic(url, "upgrade", "head")
    assert up.returncode == 0, up.stderr

    with engine.connect() as c:
        subjects = [row[0] for row in c.execute(text("SELECT subject_user_id FROM audit_logs ORDER BY id"))]
        after = c.execute(content).all()
        assignments = c.execute(text("SELECT user_id, module_key, role FROM user_module_roles")).all()
    assert subjects == [2, 1, 2, None, None, None, None]
    assert after == before  # recorded content untouched
    assert assignments == [(1, "talent-flow", "TA_MEMBER")]  # existing assignment preserved

    with pytest.raises(IntegrityError), engine.begin() as c:
        _assignment(c, 1, role="TA_MANAGER")
    tables = ("user_module_roles", "group_module_roles")
    unique = {u["name"] for table in tables for u in inspect(engine).get_unique_constraints(table)}
    assert {"uq_user_module_roles_user_module", "uq_group_module_roles_group_module"} <= unique

    # Re-running over an upgraded database changes nothing.
    assert _alembic(url, "stamp", PREVIOUS).returncode == 0
    again = _alembic(url, "upgrade", "head")
    assert again.returncode == 0, again.stderr
    with engine.connect() as c:
        assert [row[0] for row in c.execute(text("SELECT subject_user_id FROM audit_logs ORDER BY id"))] == subjects


def test_upgrade_stops_and_changes_nothing_when_duplicates_exist(at_previous):
    url, engine = at_previous
    with engine.begin() as c:
        _assignment(c, 1)
        _assignment(c, 1, role="TA_MANAGER")

    up = _alembic(url, "upgrade", "head")
    assert up.returncode != 0
    assert "Duplicate access assignments exist" in up.stderr and "Nothing was changed" in up.stderr

    with engine.connect() as c:
        assert c.execute(text("SELECT version_num FROM alembic_version")).scalar() == PREVIOUS
        assert c.execute(text("SELECT COUNT(*) FROM user_module_roles")).scalar() == 2
    assert "subject_user_id" not in {col["name"] for col in inspect(engine).get_columns("audit_logs")}


def test_downgrade_restores_the_previous_schema_and_keeps_data(at_previous):
    url, engine = at_previous
    with engine.begin() as c:
        _assignment(c, 1)
    assert _alembic(url, "upgrade", "head").returncode == 0
    down = _alembic(url, "downgrade", PREVIOUS)
    assert down.returncode == 0, down.stderr
    engine.dispose()
    fresh = create_engine(url)
    assert "subject_user_id" not in {col["name"] for col in inspect(fresh).get_columns("audit_logs")}
    with fresh.begin() as c:
        _assignment(c, 1, role="TA_MANAGER")  # constraint is gone again
        assert c.execute(text("SELECT COUNT(*) FROM user_module_roles")).scalar() == 2
    fresh.dispose()
