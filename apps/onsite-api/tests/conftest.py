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
ADMIN = VIEWER + ["onsite.health.read", "onsite.identity.read", "onsite.sync.request", "onsite.sites.manage"]
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
