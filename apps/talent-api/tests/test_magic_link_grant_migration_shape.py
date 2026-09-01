"""Verifies the ACTUAL alembic migration path (not Base.metadata.create_all)
produces the ``magic_link_grants`` table e7f8a9b0c1d2 claims: unique
``token_hash`` and ``public_id`` indexes, a ``client_id`` FK to
``clients.id``, and the plain lookup indexes. Same disposable file-backed
SQLite + real ``command.upgrade`` mechanism as
``test_promotion_migration_shape.py``.
"""

import os
import sqlite3
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command
from app.core.config import get_settings

_TALENT_API_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def migrated_db(tmp_path):
    # env.py always re-reads get_settings().database_url, and get_settings
    # is @lru_cache'd (warmed by conftest) — clear the cache, not just the
    # env var. Mirrors test_promotion_migration_shape.py.
    db_path = tmp_path / "magic_link_migration_shape.db"
    prior = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    get_settings.cache_clear()
    try:
        cfg = Config(str(_TALENT_API_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(_TALENT_API_ROOT / "alembic"))
        command.upgrade(cfg, "head")
        conn = sqlite3.connect(str(db_path))
        yield conn
        conn.close()
    finally:
        if prior is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prior
        get_settings.cache_clear()


def _indexes(conn, table):
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name=?", (table,)
    ).fetchall()
    return {name: sql for name, sql in rows}


_NOW = "2026-09-02T00:00:00"
_INSERT = (
    "INSERT INTO magic_link_grants (public_id, client_id, scope_type, contact_email, "
    "contact_name, token_hash, token_prefix, issued_by_user_id, issued_at, expires_at, "
    "use_count, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
)


def _seed_client(conn) -> int:
    return conn.execute(
        "INSERT INTO clients (platform_client_id, name, status, created_at, updated_at) "
        "VALUES (?,?,?,?,?)",
        (None, "Magic Link Shape Client", "ACTIVE", _NOW, _NOW),
    ).lastrowid


def test_table_and_indexes_exist(migrated_db):
    indexes = _indexes(migrated_db, "magic_link_grants")
    assert "ix_magic_link_grants_token_hash" in indexes
    assert "UNIQUE" in indexes["ix_magic_link_grants_token_hash"]
    assert "ix_magic_link_grants_public_id" in indexes
    assert "UNIQUE" in indexes["ix_magic_link_grants_public_id"]
    assert "ix_magic_link_grants_client_id" in indexes
    assert "ix_magic_link_grants_expires_at" in indexes


def test_token_hash_partial_none_of_it_duplicates_are_rejected(migrated_db):
    client_id = _seed_client(migrated_db)
    migrated_db.execute(
        _INSERT,
        ("mlg-a", client_id, "CLIENT_WORKSPACE", "", "", "h" * 64, "hhhh", 1, _NOW, _NOW, 0, _NOW, _NOW),
    )
    migrated_db.commit()
    with pytest.raises(sqlite3.IntegrityError):
        migrated_db.execute(
            _INSERT,
            ("mlg-b", client_id, "CLIENT_WORKSPACE", "", "", "h" * 64, "hhhh", 1, _NOW, _NOW, 0, _NOW, _NOW),
        )


def test_client_id_foreign_key_enforced(migrated_db):
    migrated_db.execute("PRAGMA foreign_keys = ON")
    with pytest.raises(sqlite3.IntegrityError):
        migrated_db.execute(
            _INSERT,
            ("mlg-x", 999999, "CLIENT_WORKSPACE", "", "", "z" * 64, "zzzz", 1, _NOW, _NOW, 0, _NOW, _NOW),
        )
