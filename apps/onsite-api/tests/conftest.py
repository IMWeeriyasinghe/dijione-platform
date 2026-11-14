"""onsite-api tests: SQLite + ``INTEGRATIONS_MODE=mock`` — no Azure SQL, no
network. People and Platform calls are stubbed per test."""

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_onsite.db")
os.environ["API_CORS_ORIGINS"] = "http://localhost:3000"
os.environ["PLATFORM_JWT_SECRET"] = "test-only-jwt-secret"
os.environ["INTERNAL_SERVICE_SECRET"] = "test-only-internal-secret"
os.environ["INTEGRATIONS_MODE"] = "mock"
os.environ["PLATFORM_API_URL"] = "http://127.0.0.1:1"
os.environ["PEOPLE_API_URL"] = "http://127.0.0.1:1"
os.environ["SYNC_SOURCE_RETRY_SECONDS"] = "0"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from jose import jwt  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import workforce_directory  # noqa: E402

VIEWER = ["onsite.dashboard.read", "onsite.attendance.read", "onsite.exceptions.read"]
ADMIN = VIEWER + ["onsite.health.read", "onsite.identity.read", "onsite.identity.manage", "onsite.sync.request",
                  "onsite.sites.manage"]
PERMS = {"ONSITE_VIEWER": VIEWER, "ONSITE_ADMIN": ADMIN}

# Mirrors the shape of people-api's Workforce Directory DTO for the codes in
# app/attendance_source/mock_client.py.
DIRECTORY = [
    {"bamboohr_id": "1", "employee_number": "101", "display_name": "A", "employment_status": "Active",
     "hire_date": "2020-01-01", "termination_date": None, "department": "Bench", "location": "Sri Lanka"},
    {"bamboohr_id": "2", "employee_number": "102", "display_name": "B", "employment_status": "Active",
     "hire_date": "2020-01-01", "termination_date": None, "department": "Bench", "location": "Sri Lanka"},
    {"bamboohr_id": "3", "employee_number": "103", "display_name": "C", "employment_status": "Inactive",
     "hire_date": "2019-01-01", "termination_date": "2025-08-31", "department": "Bench", "location": "Sri Lanka"},
    {"bamboohr_id": "5", "employee_number": "105", "display_name": "D", "employment_status": "Active",
     "hire_date": "2020-01-01", "termination_date": None, "department": "X", "location": "Sri Lanka"},
    {"bamboohr_id": "6", "employee_number": "105", "display_name": "E", "employment_status": "Active",
     "hire_date": "2020-01-01", "termination_date": None, "department": "Y", "location": "Sri Lanka"},
    {"bamboohr_id": "7", "employee_number": "0107", "display_name": "F", "employment_status": "Active",
     "hire_date": "2020-01-01", "termination_date": None, "department": "Bench", "location": "Sri Lanka"},
    {"bamboohr_id": "8", "employee_number": "108", "display_name": "G", "employment_status": "Active",
     "hire_date": "2026-12-01", "termination_date": None, "department": "Bench", "location": "Brisbane"},
    {"bamboohr_id": "10", "employee_number": "110", "display_name": "H", "employment_status": "Active",
     "hire_date": "2020-01-01", "termination_date": None, "department": "Bench", "location": "Brisbane"},
    {"bamboohr_id": "11", "employee_number": None, "display_name": "I", "employment_status": "Active",
     "hire_date": "2020-01-01", "termination_date": None, "department": "Bench", "location": "Sri Lanka"},
]


def issue_token(user_id: int = 1, role: str | None = "ONSITE_ADMIN") -> str:
    now = datetime.now(UTC)
    module_roles = {}
    if role is not None:
        module_roles["onsite"] = {"role": role, "client_id": None, "client_ids": None, "permissions": PERMS[role]}
    payload = {
        "sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=60), "iss": "dijione-dev-identity",
        "is_active": True, "full_name": "Test User", "email": f"user{user_id}@example.com",
        "platform_role": "PLATFORM_USER", "platform_permissions": [], "module_roles": module_roles,
    }
    return jwt.encode(payload, os.environ["PLATFORM_JWT_SECRET"], algorithm="HS256")


def headers_for(role: str | None = "ONSITE_ADMIN", user_id: int = 1) -> dict:
    return {"Authorization": f"Bearer {issue_token(user_id, role)}"}


def internal_headers() -> dict:
    return {"X-Internal-Token": os.environ["INTERNAL_SERVICE_SECRET"]}


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    workforce_directory.clear_cache()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def api_client():
    return TestClient(app)


@pytest.fixture()
def audit_calls(monkeypatch):
    calls = []
    from app.services import platform_audit

    monkeypatch.setattr(platform_audit, "record", lambda **kw: calls.append(kw))
    import app.api.routes.admin as admin_routes

    monkeypatch.setattr(admin_routes.platform_audit, "record", lambda **kw: calls.append(kw))
    return calls


@pytest.fixture()
def directory(monkeypatch):
    """Workforce Directory available, returning DIRECTORY."""
    snapshot = workforce_directory.DirectorySnapshot(available=True, entries=DIRECTORY)
    monkeypatch.setattr(workforce_directory, "load", lambda force=False: snapshot)
    return snapshot


def run_sync(api_client) -> dict:
    resp = api_client.post("/api/onsite/internal/scheduled-sync", headers=internal_headers())
    assert resp.status_code == 202, resp.text
    return resp.json()


def enable_site(api_client, site_id: str) -> None:
    resp = api_client.put(f"/api/onsite/admin/sites/{site_id}", json={"enabled": True}, headers=headers_for())
    assert resp.status_code == 200, resp.text


def make_mapping(db, *, site_id: str = "dev-site", code: str, bamboohr_id: str, valid_from, valid_to=None,
                 evidence: str = "synthetic test evidence", user_id: int = 1):
    """Insert a VERIFIED mapping directly (synthetic test data only)."""
    from datetime import date as _date

    from app.models.identity import IdentityMapping

    m = IdentityMapping(site_id=site_id, zk_emp_code=code, bamboohr_id=bamboohr_id,
                        valid_from=_date.fromisoformat(valid_from) if isinstance(valid_from, str) else valid_from,
                        valid_to=_date.fromisoformat(valid_to) if isinstance(valid_to, str) else valid_to,
                        status="VERIFIED", evidence=evidence, verified_by_user_id=user_id, source="MANUAL")
    db.add(m)
    db.commit()
    return m


# The synthetic verified mappings used by the read-path tests: every mock
# code that "matched" before the redesign is mapped explicitly, while "999"
# and "TEST-AZURE-001" stay unmapped. "105" is mapped to ONE of the two
# directory employees sharing Employee Number 105 (bamboohr 5), proving that
# a shared Employee Number no longer matters.
STANDARD_MAPPINGS = [
    ("dev-site", "101", "1"), ("dev-site", "102", "2"), ("dev-site", "0107", "7"), ("dev-site", "103", "3"),
    ("dev-site", "105", "5"), ("syd-site", "110", "10"), ("syd-site", "108", "8"),
]


@pytest.fixture()
def mapped(db):
    for site, code, bid in STANDARD_MAPPINGS:
        make_mapping(db, site_id=site, code=code, bamboohr_id=bid, valid_from="2020-01-01")
    return STANDARD_MAPPINGS


def map_directory(entries, sites=("dev-site", "syd-site"), valid_from="2000-01-01"):
    """Synthetic test data: register a VERIFIED mapping (code -> bamboohr_id)
    for every directory entry whose Employee Number is unique and non-blank,
    so the pre-redesign dashboard tests keep exercising the same people.
    This is explicit verified data, NOT numeric matching: the application
    never derives a mapping from an Employee Number. Shared numbers (e.g.
    "105") stay unmapped."""
    from collections import Counter
    from datetime import date as _date

    from app.models.identity import IdentityMapping

    counts = Counter(e.get("employee_number") for e in entries)
    s = SessionLocal()
    try:
        for e in entries:
            n = e.get("employee_number")
            if n is None or not str(n).strip() or counts[n] > 1:
                continue
            for site in sites:
                s.add(IdentityMapping(site_id=site, zk_emp_code=n, bamboohr_id=str(e["bamboohr_id"]),
                                      valid_from=_date.fromisoformat(valid_from), status="VERIFIED",
                                      evidence="synthetic test mapping", verified_by_user_id=1, source="MANUAL"))
        s.commit()
    finally:
        s.close()
