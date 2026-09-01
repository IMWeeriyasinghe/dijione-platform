"""Verifies the ACTUAL alembic migration path (not just Base.metadata's
create_all(), which every other test's ``db`` fixture uses) produces the
constraints d2f4a6b8c0e1 claims: candidates.email nullable + non-unique,
lever_external_id / posting_external_id / lever_opportunity_id
partial-unique. Runs against a disposable file-backed SQLite DB via the
real alembic upgrade path — the same mechanism CI's migrations.yml and
postgres.yml exercise for every service, just re-checked at the row level
here.
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
    # env.py's config.set_main_option(..., get_settings().database_url)
    # always wins over anything set on the Config object directly — and
    # get_settings() is @lru_cache'd (already warmed by conftest's own
    # DATABASE_URL for every other test in this session), so the env var
    # alone is not enough; the cache must be cleared too.
    db_path = tmp_path / "migration_shape.db"
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


def test_candidates_email_is_nullable_and_non_unique(migrated_db):
    now = "2026-09-02T00:00:00"
    migrated_db.execute(
        "INSERT INTO candidates (full_name, phone, professional_title, summary, location, "
        "availability_status, skills, cv_reference, source, lever_external_id, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        ("A", "", "", "", "", "AVAILABLE", "", "", "MANUAL", None, now, now),
    )
    migrated_db.execute(
        "INSERT INTO candidates (full_name, phone, professional_title, summary, location, "
        "availability_status, skills, cv_reference, source, lever_external_id, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        ("B", "", "", "", "", "AVAILABLE", "", "", "MANUAL", None, now, now),
    )
    migrated_db.commit()
    count = migrated_db.execute("SELECT COUNT(*) FROM candidates WHERE email IS NULL").fetchone()[0]
    assert count == 2

    indexes = _indexes(migrated_db, "candidates")
    assert "ix_candidates_email" in indexes
    assert "UNIQUE" not in indexes["ix_candidates_email"]
    assert "uq_candidates_lever_external_id" in indexes
    assert "WHERE lever_external_id IS NOT NULL" in indexes["uq_candidates_lever_external_id"]


def test_candidates_lever_external_id_partial_unique_rejects_duplicates(migrated_db):
    now = "2026-09-02T00:00:00"
    insert_sql = (
        "INSERT INTO candidates (full_name, phone, professional_title, summary, location, "
        "availability_status, skills, cv_reference, source, lever_external_id, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
    )
    migrated_db.execute(insert_sql, ("A", "", "", "", "", "AVAILABLE", "", "", "LEVER", "dup-id", now, now))
    migrated_db.commit()

    with pytest.raises(sqlite3.IntegrityError):
        migrated_db.execute(
            insert_sql, ("B", "", "", "", "", "AVAILABLE", "", "", "LEVER", "dup-id", now, now)
        )


def test_talent_requests_posting_ref_partial_unique(migrated_db):
    indexes = _indexes(migrated_db, "talent_requests")
    assert "uq_talent_requests_posting_ref" in indexes
    assert "WHERE posting_external_id IS NOT NULL" in indexes["uq_talent_requests_posting_ref"]

    now = "2026-09-02T00:00:00"
    client_id = migrated_db.execute(
        "INSERT INTO clients (platform_client_id, name, status, created_at, updated_at) "
        "VALUES (?,?,?,?,?)",
        (None, "Migration Shape Test Client", "ACTIVE", now, now),
    ).lastrowid
    migrated_db.execute(
        "INSERT INTO talent_requests (request_code, client_id, provider, posting_external_id, "
        "designation, description, required_skills, seniority, location, engagement_type, notes, "
        "current_stage, lifecycle_status, customer_success_status, ta_status, "
        "client_safe_status_text, priority, created_by, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "SR-00001", client_id, "LEVER", "p1", "Role", "", "", "", "", "FULL_TIME", "",
            "SOURCING", "IN_PROGRESS", "APPROVED", "ATS_LINKED", "Sourcing candidates",
            "MEDIUM", 0, now, now,
        ),
    )
    migrated_db.commit()

    with pytest.raises(sqlite3.IntegrityError):
        migrated_db.execute(
            "INSERT INTO talent_requests (request_code, client_id, provider, posting_external_id, "
            "designation, description, required_skills, seniority, location, engagement_type, notes, "
            "current_stage, lifecycle_status, customer_success_status, ta_status, "
            "client_safe_status_text, priority, created_by, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "SR-00002", client_id, "LEVER", "p1", "Role Again", "", "", "", "", "FULL_TIME", "",
                "SOURCING", "IN_PROGRESS", "APPROVED", "ATS_LINKED", "Sourcing candidates",
                "MEDIUM", 0, now, now,
            ),
        )


def test_applications_lever_opportunity_id_partial_unique(migrated_db):
    indexes = _indexes(migrated_db, "applications")
    assert "uq_applications_lever_opportunity_id" in indexes
    assert "WHERE lever_opportunity_id IS NOT NULL" in indexes["uq_applications_lever_opportunity_id"]
