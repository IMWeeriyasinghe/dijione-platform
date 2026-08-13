"""talent-api owns no User/UserModuleRole table, so tests can't dev-login
against a running platform-api — they mint the same signed claims Platform
Core would issue, locally, with the shared HS256 secret, and assert against
that. This exercises exactly what talent-api's ``get_talent_scope`` actually
decodes, without needing a second live service for the test suite to pass.
"""

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_talent.db"
os.environ["JWT_DEV_SECRET"] = "test-only-secret"
os.environ["API_CORS_ORIGINS"] = "http://localhost:3000"
os.environ["INTERNAL_SERVICE_SECRET"] = "test-only-internal-secret"
os.environ["INTEGRATIONS_MODE"] = "mock"
# Deliberately unroutable — talent-api's audit/notification writes to
# Platform Core must be best-effort (CR §21, §27); pointing tests at a
# reserved port makes that fallback deterministic and fast (immediate
# connection refusal) instead of depending on whether something happens to
# be listening on the real default port.
os.environ["PLATFORM_API_URL"] = "http://127.0.0.1:1"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from jose import jwt  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.client import Client  # noqa: E402

TALENT_PERMISSIONS_BY_ROLE = {
    "TALENT_CLIENT": [
        "talent.dashboard.read_own", "talent.requests.read_own", "talent.requests.create",
        "talent.candidates.read_client_safe", "talent.interviews.read_own",
        "talent.messages.read_own", "talent.messages.create",
        "talent.documents.read_own", "talent.documents.create",
    ],
    "TA_MEMBER": [
        "talent.workspace.staff", "talent.dashboard.read", "talent.clients.read",
        "talent.requests.read", "talent.requests.update", "talent.candidates.read",
        "talent.candidates.manage", "talent.applications.read", "talent.applications.create",
        "talent.applications.update", "talent.interviews.read", "talent.interviews.manage",
        "talent.messages.read", "talent.messages.create", "talent.documents.read",
        "talent.documents.create",
    ],
    "CUSTOMER_SUCCESS": [
        "talent.workspace.staff", "talent.dashboard.read", "talent.clients.read",
        "talent.requests.read", "talent.requests.update", "talent.candidates.read",
        "talent.candidates.manage", "talent.applications.read", "talent.applications.create",
        "talent.applications.update", "talent.interviews.read", "talent.interviews.manage",
        "talent.messages.read", "talent.messages.create", "talent.documents.read",
        "talent.documents.create", "talent.requests.review",
    ],
}


def issue_token(
    user_id: int, *, full_name: str = "", role: str | None = None,
    client_id: int | None = None, client_ids: list[int] | None = None,
) -> str:
    now = datetime.now(UTC)
    module_roles = {}
    if role is not None:
        module_roles["talent-flow"] = {
            "role": role, "client_id": client_id, "client_ids": client_ids,
            "permissions": TALENT_PERMISSIONS_BY_ROLE[role],
        }
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=60),
        "iss": "dijione-dev-identity",
        "is_active": True,
        "full_name": full_name,
        "email": f"user{user_id}@example.com",
        "platform_role": "PLATFORM_USER",
        "platform_permissions": [],
        "module_roles": module_roles,
    }
    return jwt.encode(payload, os.environ["JWT_DEV_SECRET"], algorithm="HS256")


def headers_for(user_id: int, **kwargs) -> dict:
    return {"Authorization": f"Bearer {issue_token(user_id, **kwargs)}"}


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def api_client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def platform_calls(monkeypatch):
    """talent-api records audit events/notifications through Platform
    Core's HTTP API (AuditService/NotificationService wrap
    ``auth_client_py.PlatformClient``) rather than a local table now, so
    tests assert against *what would have been sent*, not a local
    AuditLog/Notification row — patches the PlatformClient methods those
    services call and records every invocation.

    Autouse: every test gets this fast, in-memory stand-in by default (no
    test should pay for a real, possibly slow, connection attempt to a
    dead port just because it happened to create a talent request).
    Dedicated resilience tests that want the *real* best-effort network
    fallback undo the patch explicitly via ``monkeypatch.undo()`` or by
    constructing a ``PlatformClient`` directly.
    """
    from auth_client_py import PlatformClient

    calls = {"audit_events": [], "notifications": [], "broadcasts": []}

    def _record_audit_event(self, **kwargs):
        calls["audit_events"].append(kwargs)
        return True

    def _notify_user(self, **kwargs):
        calls["notifications"].append(kwargs)
        return True

    def _broadcast_notification(self, **kwargs):
        calls["broadcasts"].append(kwargs)
        return True

    monkeypatch.setattr(PlatformClient, "record_audit_event", _record_audit_event)
    monkeypatch.setattr(PlatformClient, "notify_user", _notify_user)
    monkeypatch.setattr(PlatformClient, "broadcast_notification", _broadcast_notification)
    return calls


@pytest.fixture()
def two_tenant_world(db):
    """Two clients, one client-user each, one TA member, one CS user —
    fixed ids chosen simply to be distinct from client ids, mirroring the
    pre-split fixture's shape."""
    abc = Client(name="ABC Company", industry="Financial Services", status="ACTIVE")
    xyz = Client(name="XYZ Company", industry="Retail", status="ACTIVE")
    db.add_all([abc, xyz])
    db.commit()

    return {
        "abc": abc,
        "xyz": xyz,
        "abc_user_id": 101,
        "xyz_user_id": 102,
        "ta_user_id": 103,
        "cs_user_id": 104,
        "abc_headers": headers_for(101, full_name="ABC Client User", role="TALENT_CLIENT", client_id=abc.id),
        "xyz_headers": headers_for(102, full_name="XYZ Client User", role="TALENT_CLIENT", client_id=xyz.id),
        "ta_headers": headers_for(103, full_name="TA User", role="TA_MEMBER"),
        "cs_headers": headers_for(104, full_name="CS User", role="CUSTOMER_SUCCESS"),
    }
