"""0003_onsite_attendance_reviews — additive, upgrade-from-current with data,
constraints/indexes present, downgrade (CI only) removes only the review
tables. The same alembic sequence runs on PostgreSQL in the CI ``upgrade`` /
``pg`` legs; set ONSITE_PG_URL to run it here against a local server."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[1]
REVIEW_TABLES = {"onsite_attendance_reviews", "onsite_attendance_review_events"}


def _alembic(url: str, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": url}
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, env=env, check=True, capture_output=True)


def _seed_v08(eng) -> None:
    """Rows a v0.8 database already holds (synthetic): a fingerprint and a verified mapping."""
    with eng.begin() as c:
        c.execute(sa.text(
            "INSERT INTO attendance_events (event_id, site_id, source_epoch, source_transaction_id, emp_code, "
            "punch_time_local, punch_time_utc, time_zone, captured_at_utc, received_utc, batch_id, record_hash, "
            "site_local_date, sync_run_id, mirrored_at) VALUES ('s:1:1','s',1,1,'101','2026-10-13T08:30:00+05:30',"
            "'2026-10-13 03:00:00','Asia/Colombo','2026-10-13 03:00:00','2026-10-13 03:00:00','b','h',"
            "'2026-10-13','r','2026-10-13 03:00:00')"))
        c.execute(sa.text(
            "INSERT INTO onsite_identity_mappings (site_id, zk_emp_code, bamboohr_id, valid_from, status, evidence, "
            "verified_by_user_id, verified_at, source, created_at, updated_at) VALUES ('s','101','1','2020-01-01',"
            "'VERIFIED','synthetic',1,'2026-10-01 00:00:00','MANUAL','2026-10-01 00:00:00','2026-10-01 00:00:00')"))


def _check(url: str) -> None:
    _alembic(url, "upgrade", "0002_onsite_identity")
    eng = sa.create_engine(url)
    _seed_v08(eng)
    eng.dispose()
    _alembic(url, "upgrade", "head")  # upgrade-from-current with data
    eng = sa.create_engine(url)
    insp = sa.inspect(eng)
    assert REVIEW_TABLES <= set(insp.get_table_names())
    uniques = {u["name"]: u["column_names"] for u in insp.get_unique_constraints("onsite_attendance_reviews")}
    assert uniques["uq_review_identity_day"] == ["site_id", "local_date", "identity_key"]
    idx = {i["name"] for i in insp.get_indexes("onsite_attendance_reviews")}
    assert {"ix_review_site_date", "ix_review_site_status"} <= idx
    assert "ix_review_event_review_at" in {i["name"] for i in insp.get_indexes("onsite_attendance_review_events")}
    checks = {c["name"] for c in insp.get_check_constraints("onsite_attendance_reviews")}
    assert {"ck_review_kind", "ck_review_status", "ck_review_type", "ck_review_version"} <= checks
    with eng.connect() as c:  # existing data untouched
        assert c.execute(sa.text("select count(*) from attendance_events")).scalar() == 1
        assert c.execute(sa.text("select count(*) from onsite_identity_mappings")).scalar() == 1
        assert c.execute(sa.text("select version_num from alembic_version")).scalar() == \
            "0003_onsite_attendance_reviews"
    eng.dispose()
    _alembic(url, "downgrade", "0002_onsite_identity")  # CI only — never live
    eng = sa.create_engine(url)
    assert not REVIEW_TABLES & set(sa.inspect(eng).get_table_names())
    with eng.connect() as c:
        assert c.execute(sa.text("select count(*) from attendance_events")).scalar() == 1
    eng.dispose()
    _alembic(url, "upgrade", "head")


def test_sqlite_upgrade_from_current_with_data(tmp_path):
    _check(f"sqlite:///{tmp_path / 'v08.db'}")


@pytest.mark.skipif(not os.environ.get("ONSITE_PG_URL"), reason="set ONSITE_PG_URL to a disposable database")
def test_postgres_upgrade_from_current_with_data():
    _check(os.environ["ONSITE_PG_URL"])
