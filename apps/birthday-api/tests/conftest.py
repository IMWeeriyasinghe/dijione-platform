import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_birthday.db"
os.environ["JWT_DEV_SECRET"] = "test-only-secret"
os.environ["API_CORS_ORIGINS"] = "http://localhost:3000"
os.environ["INTERNAL_SERVICE_SECRET"] = "test-only-internal-secret"
os.environ["INTEGRATIONS_MODE"] = "mock"
# Deliberately unroutable — best-effort audit/notification calls to
# Platform Core must not slow down or fail the test suite.
os.environ["PLATFORM_API_URL"] = "http://127.0.0.1:1"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from jose import jwt  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

# Tables must exist even for tests that hit routes without taking the `db`
# fixture explicitly (e.g. GET /api/birthday/summary) — the `db` fixture
# below still drops/recreates for full isolation on tests that need it.
Base.metadata.create_all(bind=engine)

BIRTHDAY_PERMISSIONS_BY_ROLE = {
    "BIRTHDAY_USER": [
        "birthday.dashboard.read", "birthday.orders.read", "birthday.suppliers.read",
    ],
    "BIRTHDAY_ADMIN": [
        "birthday.dashboard.read", "birthday.orders.read", "birthday.orders.create",
        "birthday.orders.update", "birthday.orders.hold_release", "birthday.orders.cancel",
        "birthday.orders.send_supplier", "birthday.orders.approve", "birthday.orders.delete",
        "birthday.suppliers.read", "birthday.suppliers.manage",
        "birthday.config.manage",
    ],
}
BIRTHDAY_PERMISSIONS_BY_ROLE["BIRTHDAY_SUPPLIER"] = ["birthday.portal.access", "birthday.portal.respond"]


def issue_token(
    user_id: int, full_name: str = "Test User", *, role: str | None = None,
    supplier_id: int | None = None, supplier_user_id: int | None = None,
) -> str:
    now = datetime.now(UTC)
    module_roles = {}
    if role is not None:
        module_roles["birthday"] = {
            "role": role, "client_id": None, "client_ids": None,
            "permissions": BIRTHDAY_PERMISSIONS_BY_ROLE[role],
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
    if supplier_id is not None:
        payload["supplier"] = {
            "supplier_id": supplier_id, "supplier_user_id": supplier_user_id or user_id,
        }
    return jwt.encode(payload, os.environ["JWT_DEV_SECRET"], algorithm="HS256")


def headers_for(user_id: int, **kwargs) -> dict:
    return {"Authorization": f"Bearer {issue_token(user_id, **kwargs)}"}


def supplier_headers_for(db, supplier, *, email: str | None = None, status: str = "ACTIVE") -> dict:
    """Dev-persona-equivalent test helper (Phase-Next §5): resolves through
    the same SupplierScope claim shape production Entra B2B tokens will
    carry — never lets the caller pick supplier_id at the request layer.

    Creates (or requires) a real ``SupplierUser`` row, since
    ``get_supplier_scope`` re-validates against the DB on every request
    (an inactive/deleted SupplierUser must lose access immediately, not
    only once their token expires) — a token can no longer be minted for
    an id that doesn't exist in the database, matching production."""
    from app.models.supplier_user import SupplierUser

    user = SupplierUser(
        supplier_id=supplier.id,
        email=email or f"supplier-user-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Test Supplier User",
        status=status,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return headers_for(
        user.id, role="BIRTHDAY_SUPPLIER", supplier_id=supplier.id, supplier_user_id=user.id,
    )


@pytest.fixture()
def api_client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def platform_calls(monkeypatch):
    """birthday-api records audit events/notifications through Platform
    Core's HTTP API rather than a local table — patches PlatformClient so
    tests don't pay for (or depend on) a real network call. Mirrors
    talent-api's identical fixture."""
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
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
