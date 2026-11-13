"""Stage 1: Alembic upgrade -> downgrade base -> upgrade on a fresh SQLite file
(the same sequence CI runs on Postgres). CI-only downgrade; never live."""

import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[1]


def _alembic(url: str, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": url}
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, env=env, check=True, capture_output=True)


def test_upgrade_downgrade_upgrade(tmp_path):
    url = f"sqlite:///{tmp_path / 'mig.db'}"
    _alembic(url, "upgrade", "head")
    eng = sa.create_engine(url)
    insp = sa.inspect(eng)
    tables = set(insp.get_table_names())
    assert {"onsite_identity_mappings", "onsite_identity_rejections", "onsite_identity_events",
            "attendance_events"} <= tables
    idx = {i["name"]: i for i in insp.get_indexes("onsite_identity_mappings")}
    assert idx["ux_idmap_open_verified"]["unique"]
    with eng.connect() as c:
        assert c.execute(sa.text("select version_num from alembic_version")).scalar() == "0002_onsite_identity"
    eng.dispose()
    _alembic(url, "downgrade", "base")
    eng = sa.create_engine(url)
    assert "onsite_identity_mappings" not in sa.inspect(eng).get_table_names()
    eng.dispose()
    _alembic(url, "upgrade", "head")
    eng = sa.create_engine(url)
    assert "onsite_identity_mappings" in sa.inspect(eng).get_table_names()
    eng.dispose()


def test_model_metadata_matches_migration(tmp_path):
    """The ORM model and the migration declare the same identity columns."""
    url = f"sqlite:///{tmp_path / 'mig2.db'}"
    _alembic(url, "upgrade", "head")
    eng = sa.create_engine(url)
    import app.models  # noqa: F401
    from app.db.base import Base

    insp = sa.inspect(eng)
    for table in ("onsite_identity_mappings", "onsite_identity_rejections", "onsite_identity_events"):
        migrated = {c["name"] for c in insp.get_columns(table)}
        assert migrated == set(Base.metadata.tables[table].columns.keys()), table
    eng.dispose()
