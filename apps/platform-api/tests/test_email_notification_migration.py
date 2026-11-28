"""Migration t2u4w6y8a0c2: email outbox tables — additive, single head, reversible, no data touched."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

APP_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS, THIS = "s1t3v5x7z9b1", "t2u4w6y8a0c2"
TABLES = {"email_outbox", "user_access_snapshots", "notification_event_settings", "email_test_recipients"}


def _alembic(url, *args):
    env = {**os.environ, "DATABASE_URL": url, "APP_ENV": "production"}
    env.pop("PYTHONPATH", None)
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=APP_ROOT, env=env, capture_output=True, text=True)


def _users(engine):
    with engine.connect() as c:
        return c.execute(text("SELECT id, email, is_active, access_version FROM users ORDER BY id")).all()


def test_single_head_upgrade_adds_only_the_new_tables_and_downgrade_removes_them(tmp_path):
    url = f"sqlite:///{tmp_path / 'mail.db'}"
    heads = _alembic(url, "heads")
    assert heads.returncode == 0, heads.stderr
    assert heads.stdout.split() == ["w5x7z9b1d3f5", "(head)"]  # single head

    assert _alembic(url, "upgrade", PREVIOUS).returncode == 0
    engine = create_engine(url)
    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO users (id, email, full_name, platform_role, is_active, identity_provider, internal_employee,"
            " access_version, created_at, updated_at) VALUES (1, 'a@example.com', 'A', 'PLATFORM_USER', 1, 'ENTRA', 0,"
            " 7, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ))
    before_tables, before_users = set(inspect(engine).get_table_names()), _users(engine)

    result = _alembic(url, "upgrade", THIS)
    assert result.returncode == 0, result.stderr
    engine.dispose()
    after = set(inspect(engine).get_table_names())
    assert after - before_tables == TABLES
    assert _users(engine) == before_users  # no row touched, no access_version raised
    outbox = {c["name"] for c in inspect(engine).get_columns("email_outbox")}
    assert {"correlation_id", "dedupe_key", "status", "attempts", "not_before", "transport_outcome"} <= outbox
    with engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM email_outbox")).scalar() == 0

    result = _alembic(url, "downgrade", PREVIOUS)
    assert result.returncode == 0, result.stderr
    engine.dispose()
    assert set(inspect(engine).get_table_names()) == before_tables
    assert _users(engine) == before_users


def test_notification_permissions_migration_links_super_and_platform_admin_only(tmp_path):
    url = f"sqlite:///{tmp_path / 'perm.db'}"
    result = _alembic(url, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    engine = create_engine(url)
    with engine.connect() as c:
        linked = c.execute(text(
            "SELECT p.key, r.key FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id"
            " JOIN roles r ON r.id = rp.role_id WHERE p.key LIKE 'platform.admin.%_notifications'"
        )).all()
    keys = {"platform.admin.view_notifications", "platform.admin.manage_notifications"}
    assert {p for p, _ in linked} == keys
    assert set(linked) == {(p, r) for p in keys for r in ("SUPER_ADMIN", "PLATFORM_ADMIN")}
    assert _alembic(url, "upgrade", "head").returncode == 0  # re-run is safe


def test_birthday_display_name_migration_is_idempotent_and_reversible(tmp_path):
    url = f"sqlite:///{tmp_path / 'name.db'}"
    assert _alembic(url, "upgrade", "u3v5x7z9b1d3").returncode == 0
    engine = create_engine(url)

    def name():
        with engine.connect() as c:
            return c.execute(text("SELECT key, name FROM application_modules WHERE key = 'birthday'")).all()

    with engine.begin() as c:
        if not name():
            c.execute(text(
                "INSERT INTO application_modules (key, name, description, icon, route, status, enabled, display_order,"
                " required_roles, supports_client_scope, created_at, updated_at) VALUES ('birthday', 'DijiBirthday',"
                " '', 'Gift', '/birthday', 'ACTIVE', 1, 2, 'ANY', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
    before = name()
    assert before == [("birthday", "DijiBirthday")]
    assert _alembic(url, "upgrade", "head").returncode == 0
    engine.dispose()
    assert name() == [("birthday", "DIJI Birthday")]
    assert _alembic(url, "upgrade", "head").returncode == 0  # re-run is safe
    assert _alembic(url, "downgrade", "u3v5x7z9b1d3").returncode == 0
    engine.dispose()
    assert name() == before
