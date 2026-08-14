"""Phase A domain model tests: the DB-level idempotency constraint on
BirthdayOrder(employee_id, birthday_year) and the Alembic upgrade/downgrade
round-trip."""

import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.birthday_order import BirthdayOrder

APP_ROOT = Path(__file__).resolve().parents[1]


def _make_order(employee_id: str, birthday_year: int, order_reference: str) -> BirthdayOrder:
    return BirthdayOrder(
        order_reference=order_reference,
        employee_id=employee_id,
        employee_name="Ayesha Wijeratne",
        employee_email="ayesha.wijeratne@example.com",
        birthday_date=date(birthday_year, 6, 15),
        birthday_year=birthday_year,
        office_location="Colombo",
        lead_time_days=12,
        lead_time_class="NORMAL",
    )


def test_duplicate_employee_year_order_raises_integrity_error(db):
    db.add(_make_order("EMP1042", 2026, "BDAY-EMP1042-2026-00001"))
    db.commit()

    db.add(_make_order("EMP1042", 2026, "BDAY-EMP1042-2026-00002"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_same_employee_different_year_is_allowed(db):
    db.add(_make_order("EMP1042", 2026, "BDAY-EMP1042-2026-00001"))
    db.add(_make_order("EMP1042", 2027, "BDAY-EMP1042-2027-00001"))
    db.commit()

    count = db.query(BirthdayOrder).filter(BirthdayOrder.employee_id == "EMP1042").count()
    assert count == 2


def test_alembic_upgrade_head_then_downgrade_base_round_trips_cleanly(tmp_path):
    db_file = tmp_path / "alembic_roundtrip.db"
    env = {
        "DATABASE_URL": f"sqlite:///{db_file}",
        "JWT_DEV_SECRET": "test-only-secret",
        "API_CORS_ORIGINS": "http://localhost:3000",
        "INTERNAL_SERVICE_SECRET": "test-only-internal-secret",
        "INTEGRATIONS_MODE": "mock",
        "PLATFORM_API_URL": "http://127.0.0.1:1",
    }
    import os

    full_env = {**os.environ, **env}

    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=APP_ROOT, env=full_env, capture_output=True, text=True,
    )
    assert upgrade.returncode == 0, upgrade.stderr

    downgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "base"],
        cwd=APP_ROOT, env=full_env, capture_output=True, text=True,
    )
    assert downgrade.returncode == 0, downgrade.stderr
