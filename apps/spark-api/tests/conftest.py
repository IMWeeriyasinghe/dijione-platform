import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

os.environ["JWT_DEV_SECRET"] = "test-only-secret"
os.environ["API_CORS_ORIGINS"] = "http://localhost:3000"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from jose import jwt  # noqa: E402

from app.main import app  # noqa: E402


def issue_token(user_id: int, full_name: str = "Test User") -> str:
    now = datetime.now(UTC)
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
        "module_roles": {},
    }
    return jwt.encode(payload, os.environ["JWT_DEV_SECRET"], algorithm="HS256")


@pytest.fixture()
def api_client():
    return TestClient(app)
