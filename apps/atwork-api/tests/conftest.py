import os
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

os.environ["APP_ENV"] = "test"
os.environ["PLATFORM_JWT_SECRET"] = "test-only-secret"
os.environ["INTERNAL_SERVICE_SECRET"] = "test-only-internal-secret"
os.environ["API_CORS_ORIGINS"] = "http://localhost:3000"
os.environ["INTEGRATIONS_MODE"] = "mock"
# ATWORK_TEST_DATABASE_URL runs the suite on a disposable PostgreSQL. It drops every table.
os.environ["DATABASE_URL"] = (
    os.environ.get("ATWORK_TEST_DATABASE_URL") or f"sqlite:///{tempfile.mkdtemp(prefix='atwork-test-')}/test.db"
)
os.environ["BUSINESS_TIME_ZONE"] = "Asia/Colombo"
os.environ["PLATFORM_API_URL"] = "http://127.0.0.1:1"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from jose import jwt  # noqa: E402

from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

ISSUER = "dijione-dev-identity"


def issue_token(
    user_id: int = 7,
    *,
    module_roles: dict | None = None,
    is_active: bool = True,
    secret: str | None = None,
    issuer: str = ISSUER,
    expires_in_minutes: int = 60,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=expires_in_minutes),
        "iss": issuer,
        "is_active": is_active,
        "full_name": "Test User",
        "email": f"user{user_id}@example.com",
        "platform_role": "PLATFORM_USER",
        "platform_permissions": [],
        "module_roles": module_roles or {},
    }
    return jwt.encode(payload, secret or os.environ["PLATFORM_JWT_SECRET"], algorithm="HS256")


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture()
def api_client():
    return TestClient(app)
