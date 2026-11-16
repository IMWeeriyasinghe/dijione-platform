"""spark-api has a complete revocation route policy and refuses a revoked session."""

import os
from datetime import UTC, datetime, timedelta

import pytest
from auth_client_py.revocation import RevocationGuard, set_guard
from fastapi.routing import APIRoute
from jose import jwt

from app.core.revocation_policy import ROUTE_POLICY
from app.main import app


@pytest.fixture(autouse=True)
def _no_guard_afterwards():
    yield
    set_guard(None)


def _walk(router):
    for route in router.routes:
        if isinstance(route, APIRoute):
            yield route
        elif hasattr(route, "original_router"):
            yield from _walk(route.original_router)


def _token(av):
    now = datetime.now(UTC)
    body = {
        "sub": "5", "iat": now, "exp": now + timedelta(hours=1), "iss": "dijione-dev-identity", "is_active": True,
        "full_name": "P", "email": "p@example.com", "av": av, "platform_role": "PLATFORM_USER",
        "platform_permissions": [], "module_roles": {},
    }
    return {"Authorization": "Bearer " + jwt.encode(body, os.environ["PLATFORM_JWT_SECRET"], algorithm="HS256")}


def test_every_route_is_classified_and_no_classification_is_stale():
    actual = {f"{m} {r.path}" for r in _walk(app.router) for m in r.methods - {"HEAD", "OPTIONS"}}
    assert actual - set(ROUTE_POLICY) == set() and set(ROUTE_POLICY) - actual == set()


def test_a_revoked_session_is_refused_and_a_current_one_is_not(api_client):
    guard = RevocationGuard(lambda etag: (200, "e", {5: (3, True)}))
    guard.refresh_once()
    set_guard(guard)
    revoked = api_client.get("/api/spark/whoami", headers=_token(av=1))
    assert revoked.status_code == 401 and revoked.headers["x-auth-error"] == "session_revoked"
    assert api_client.get("/api/spark/whoami", headers=_token(av=3)).status_code == 200
