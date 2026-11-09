import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

SERVICE_ROOT = Path(__file__).resolve().parents[1]
TABLES = {"attendance_sessions", "attendance_breaks", "attendance_events"}


def alembic(url, *args):
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=SERVICE_ROOT,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
    )


def test_upgrade_constraints_downgrade_and_reupgrade(tmp_path):
    url = f"sqlite:///{tmp_path / 'migration.db'}"
    heads = alembic(url, "heads")
    assert heads.stdout.split() == ["0001_atwork_attendance", "(head)"]
    up = alembic(url, "upgrade", "head")
    assert up.returncode == 0, up.stderr
    engine = create_engine(url)
    assert TABLES <= set(inspect(engine).get_table_names())

    insert = text(
        "INSERT INTO attendance_sessions (id, platform_user_id, work_mode, status, check_in_at, time_zone, check_in_request_id,"
        " created_by_user_id, updated_by_user_id, version, created_at, updated_at)"
        " VALUES (:id, 1, 'OFFICE', 'OPEN', '2026-11-09', 'Asia/Colombo', :id, 1, 1, 1, '2026-11-09', '2026-11-09')"
    )
    with engine.begin() as conn:
        conn.execute(insert, {"id": "one"})
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(insert, {"id": "two"})
    engine.dispose()

    check = alembic(url, "check")
    assert check.returncode == 0, check.stdout + check.stderr

    down = alembic(url, "downgrade", "base")
    assert down.returncode == 0, down.stderr
    assert not TABLES & set(inspect(create_engine(url)).get_table_names())
    assert alembic(url, "upgrade", "head").returncode == 0
