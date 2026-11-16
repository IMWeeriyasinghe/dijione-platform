"""Session revocation is enforced on every route that authenticates a user, and the
sensitive-permission gate is wired into this service's permission factories."""

import inspect
import os
import re
from datetime import UTC, datetime, timedelta

import pytest
from auth_client_py.revocation import RevocationGuard, set_guard
from jose import jwt

from app.api.deps import require_onsite_permission
from app.main import app

SECRET = os.environ["PLATFORM_JWT_SECRET"]
USER_ID = 5


@pytest.fixture(autouse=True)
def _no_guard_afterwards():
    yield
    set_guard(None)


def _staff_headers(av):
    now = datetime.now(UTC)
    body = {
        "sub": str(USER_ID), "iat": now, "exp": now + timedelta(hours=1), "iss": "dijione-dev-identity",
        "is_active": True, "full_name": "Staff Person", "email": "staff@example.com", "av": av,
        "platform_role": "PLATFORM_USER", "platform_permissions": [], "module_roles": {},
    }
    return {"Authorization": "Bearer " + jwt.encode(body, SECRET, algorithm="HS256")}


def _routes_requiring_a_token(api_client):
    found = []
    for raw_path, operations in app.openapi()["paths"].items():
        path = re.sub(r"\{[^}]+\}", "1", raw_path)
        for method in sorted(m.upper() for m in operations):
            if api_client.request(method, path).status_code == 401:
                found.append((method, path))
    return found


def _guard(users, *, loaded=True):
    clock = [0.0]
    guard = RevocationGuard(lambda etag: (200, "e", users), clock=lambda: clock[0])
    if loaded:
        guard.refresh_once()
    set_guard(guard)
    return guard


def test_a_revoked_session_is_refused_by_every_authenticated_route(api_client, db):
    routes = _routes_requiring_a_token(api_client)
    _guard({USER_ID: (3, True)})
    marked = 0
    for method, path in routes:
        resp = api_client.request(method, path, headers=_staff_headers(av=1))
        assert resp.status_code == 401, f"{method} {path}: {resp.status_code}"
        marked += resp.headers.get("x-auth-error") == "session_revoked"
    assert marked >= 20, f"only {marked} of {len(routes)} routes reported a revoked session"


def test_an_inactive_account_is_refused_whatever_its_version(api_client, db):
    _guard({USER_ID: (0, False)})
    routes = [r for r in _routes_requiring_a_token(api_client) if r[0] == "GET"]
    assert routes
    refused = [
        r for r in routes
        if api_client.request(*r, headers=_staff_headers(av=50)).headers.get("x-auth-error") == "session_revoked"
    ]
    assert len(refused) >= 1


def test_with_no_snapshot_changes_are_refused_and_reads_are_not_blocked_by_revocation(api_client, db):
    routes = _routes_requiring_a_token(api_client)
    _guard({}, loaded=False)  # a cold start that could not reach platform-api
    restricted_writes = 0
    for method, path in routes:
        resp = api_client.request(method, path, headers=_staff_headers(av=0))
        flag = resp.headers.get("x-auth-error")
        if method in ("GET", "HEAD", "OPTIONS"):
            assert flag != "revocation_restricted", f"{method} {path} was blocked by revocation state"
        else:
            restricted_writes += flag == "revocation_restricted"
    assert restricted_writes >= 5


@pytest.mark.parametrize("factory", [require_onsite_permission])
def test_sensitive_permissions_carry_the_freshness_gate(factory):
    def gates(key):
        return {
            getattr(p.default, "dependency", None).__name__
            for p in inspect.signature(factory(key)).parameters.values()
            if getattr(p.default, "dependency", None) is not None
        }

    for key in ("things.manage", "things.admin", "things.approve", "things.export"):
        assert "require_fresh_revocation" in gates(key)
    assert "require_fresh_revocation" not in gates("things.read")
