"""recruitment-api owns its own database and the Lever adapters. Tests run
against SQLite with ``INTEGRATIONS_MODE=mock`` — no Lever credential, no
network. Claims are minted locally with the shared HS256 secret, exactly
as talent-api's suite does.
"""

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_recruitment.db"
os.environ["JWT_DEV_SECRET"] = "test-only-secret"
os.environ["API_CORS_ORIGINS"] = "http://localhost:3000"
os.environ["INTERNAL_SERVICE_SECRET"] = "test-only-internal-secret"
os.environ["INTEGRATIONS_MODE"] = "mock"
os.environ["PLATFORM_API_URL"] = "http://127.0.0.1:1"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app

# talent-flow staff permission set — recruitment-api's ad-hoc sync route is
# gated on a staff claim from a consuming application.
_STAFF_PERMS = ["talent.workspace.staff", "talent.integrations.sync"]


def issue_token(user_id: int = 1, *, role: str = "TA_MEMBER", permissions: list[str] | None = None) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(minutes=60),
            "iss": "dijione-dev-identity",
            "is_active": True,
            "full_name": f"User {user_id}",
            "email": f"user{user_id}@example.com",
            "platform_role": "PLATFORM_USER",
            "platform_permissions": [],
            "module_roles": {
                "talent-flow": {
                    "role": role,
                    "client_id": None,
                    "client_ids": None,
                    "permissions": permissions if permissions is not None else _STAFF_PERMS,
                }
            },
        },
        os.environ["JWT_DEV_SECRET"],
        algorithm="HS256",
    )


def staff_headers(**kwargs) -> dict:
    return {"Authorization": f"Bearer {issue_token(**kwargs)}"}


def internal_headers() -> dict:
    return {"X-Internal-Token": os.environ["INTERNAL_SERVICE_SECRET"]}


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
