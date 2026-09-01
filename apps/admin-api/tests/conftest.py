"""admin-api owns no database and no business rules of its own — its job is
forwarding, error-translation and enrichment. These tests exercise exactly
that, against lightweight stub upstreams wired in over ``httpx.ASGITransport``
(fast, in-process, no sockets).

The stubs are hand-rolled FastAPI apps rather than the real platform-api/
talent-api packages for a concrete reason: every DijiOne backend service's
top-level Python package is named ``app`` (a deliberate convention — see
docs/platform/service-architecture.md), so importing two real services'
``app.main`` into the same test process would collide in ``sys.modules``.
Platform Core's own business rules (SUPER_ADMIN lockout, permission gating,
audit logging) are already covered by ``apps/platform-api/tests`` — these
tests only need upstreams that respond with the right *shape*.
"""

import os
import sys
from pathlib import Path

os.environ["INTERNAL_SERVICE_SECRET"] = "test-only-internal-secret"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from auth_client_py import PlatformClient  # noqa: E402
from fastapi import FastAPI, Header, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import platform_gateway, talent_gateway  # noqa: E402

STUB_USERS = {
    1: {
        "id": 1, "email": "abc-user@example.com", "full_name": "ABC User", "title": None,
        "platform_role": "PLATFORM_USER", "is_active": True, "identity_provider": "DEV_IDENTITY",
        "entra_object_id": None, "last_login_at": None, "created_at": "2026-01-01T00:00:00Z",
        "module_assignments": [
            {
                "module_key": "talent-flow", "module_name": "DijiTalentFlow", "role": "TALENT_CLIENT",
                "role_name": "Talent Client", "enabled": True,
                # Platform Core resolves names itself now (§6.1).
                "client_scope": {"all_clients": False, "client_ids": [1], "client_names": ["ABC Company"]},
            }
        ],
    },
}


def _build_stub_platform_app() -> FastAPI:
    """Mimics the slice of platform-api's ``/api/platform/admin/*`` and
    ``/api/auth/*`` contract admin-api depends on."""
    stub = FastAPI()

    def _require_admin_token(authorization: str | None = Header(default=None)) -> None:
        if authorization != "Bearer valid-admin-token":
            raise HTTPException(403, "Platform admin access required")

    @stub.get("/api/platform/admin/dashboard")
    def dashboard(authorization: str | None = Header(default=None)) -> dict:
        _require_admin_token(authorization)
        return {
            "total_users": 1, "active_users": 1, "platform_admins": 1, "super_admins": 1,
            "active_modules": 3, "pending_talent_requests": 0,
        }

    @stub.get("/api/platform/admin/users")
    def list_users(authorization: str | None = Header(default=None)) -> list[dict]:
        _require_admin_token(authorization)
        return [STUB_USERS[1]]

    @stub.get("/api/platform/admin/users/{user_id}")
    def get_user(user_id: int, authorization: str | None = Header(default=None)) -> dict:
        _require_admin_token(authorization)
        if user_id not in STUB_USERS:
            raise HTTPException(404, f"User {user_id} not found")
        return STUB_USERS[user_id]

    @stub.get("/api/platform/admin/groups")
    def list_groups(authorization: str | None = Header(default=None)) -> list[dict]:
        _require_admin_token(authorization)
        return [
            {
                "id": 1, "key": "ta-team", "display_name": "TA Team", "description": "", "status": "ACTIVE",
                "group_type": "TEAM", "member_count": 1, "module_count": 1,
                "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
            }
        ]

    @stub.get("/api/platform/admin/clients")
    def list_clients(authorization: str | None = Header(default=None)) -> list[dict]:
        _require_admin_token(authorization)
        return [
            {
                "id": 1, "public_id": "cli-abc-company", "name": "ABC Company",
                "status": "ACTIVE", "created_at": "2026-01-01T00:00:00Z",
            },
            {
                "id": 2, "public_id": "cli-xyz-company", "name": "XYZ Company",
                "status": "ACTIVE", "created_at": "2026-01-01T00:00:00Z",
            },
        ]

    @stub.get("/api/platform/admin/applications/{module_key}")
    def application_detail(module_key: str, authorization: str | None = Header(default=None)) -> dict:
        _require_admin_token(authorization)
        return {
            "module_key": module_key, "module_name": "DijiTalentFlow", "description": "d", "status": "ACTIVE",
            "enabled": True,
            "assigned_users": [
                {
                    "user_id": 1, "email": "abc-user@example.com", "full_name": "ABC User",
                    "role": "TALENT_CLIENT", "role_name": "Talent Client", "enabled": True,
                    "client_scope": {"all_clients": False, "client_ids": [1], "client_names": ["ABC Company"]},
                }
            ],
            "assigned_groups": [],
            "direct_user_count": 1, "group_count": 0,
        }

    return stub


def _build_stub_talent_app() -> FastAPI:
    stub = FastAPI()

    @stub.get("/api/talent/summary")
    def summary() -> dict:
        return {"service": "talent-api", "status": "healthy", "pending_requests": 4}

    return stub


@pytest.fixture()
def stub_clients():
    # starlette's TestClient *is* an httpx.Client subclass with a sync
    # `.request()` that bridges to the ASGI app — httpx.ASGITransport itself
    # is async-only and can't back a sync httpx.Client directly.
    platform_httpx = TestClient(_build_stub_platform_app(), base_url="http://platform-api")
    talent_httpx = TestClient(_build_stub_talent_app(), base_url="http://talent-api")

    platform_client = PlatformClient(base_url="http://platform-api", internal_secret="unused", client=platform_httpx)
    talent_client = PlatformClient(
        base_url="http://talent-api", internal_secret=os.environ["INTERNAL_SERVICE_SECRET"], client=talent_httpx
    )

    app.dependency_overrides[platform_gateway.get_platform_client] = lambda: platform_client
    app.dependency_overrides[talent_gateway.get_talent_client] = lambda: talent_client
    yield
    app.dependency_overrides.clear()
    platform_httpx.close()
    talent_httpx.close()


@pytest.fixture()
def api_client(stub_clients):
    return TestClient(app)
