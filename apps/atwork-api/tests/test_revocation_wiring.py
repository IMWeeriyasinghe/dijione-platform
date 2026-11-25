"""Session revocation is enforced on every route that authenticates a user, and this
service's route policy (``app/core/revocation_policy.py``) is complete and sound."""

import inspect
import os
import re
from datetime import UTC, datetime, timedelta

import pytest
from auth_client_py import fastapi_deps
from auth_client_py.revocation import RevocationGuard, set_guard
from fastapi.routing import APIRoute
from jose import jwt

from app.core.revocation_policy import ROUTE_POLICY
from app.main import app

SECRET = os.environ["PLATFORM_JWT_SECRET"]
USER_ID = 5
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@pytest.fixture(autouse=True)
def _no_guard_afterwards():
    yield
    set_guard(None)


def _staff_headers(av):
    now = datetime.now(UTC)
    body = {
        "sub": str(USER_ID),
        "iat": now,
        "exp": now + timedelta(hours=1),
        "iss": "dijione-dev-identity",
        "is_active": True,
        "full_name": "Staff Person",
        "email": "staff@example.com",
        "av": av,
        "platform_role": "PLATFORM_USER",
        "platform_permissions": [],
        "module_roles": {},
    }
    return {"Authorization": "Bearer " + jwt.encode(body, SECRET, algorithm="HS256")}


def _walk(router):
    for route in router.routes:
        if isinstance(route, APIRoute):
            yield route
        elif hasattr(route, "original_router"):
            yield from _walk(route.original_router)


def _actual_routes():
    return {
        f"{method} {route.path}": route for route in _walk(app.router) for method in sorted(route.methods - {"HEAD", "OPTIONS"})
    }


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


# --- the policy itself ---------------------------------------------------------------


def test_every_route_is_classified_and_no_classification_is_stale():
    actual = set(_actual_routes())
    assert actual - set(ROUTE_POLICY) == set(), "routes missing from ROUTE_POLICY: classify them"
    assert set(ROUTE_POLICY) - actual == set(), "ROUTE_POLICY entries for routes that no longer exist"


def test_the_method_is_never_the_deciding_factor():
    routes = _actual_routes()
    assert not [k for k in ROUTE_POLICY if k.startswith("GET ") and ROUTE_POLICY[k] == "WRITE"]
    # Changes are never READ.
    assert [k for k, v in ROUTE_POLICY.items() if v == "READ" and k.split()[0] in WRITE_METHODS] == []
    # A GET whose handler writes is not READ, unless named here with a reason.
    writes = re.compile(r"\.commit\(|\.add\(|\.delete\(|\.merge\(")
    allowed_reads = set()
    offenders = [
        key
        for key, route in routes.items()
        if key.startswith("GET ")
        and ROUTE_POLICY[key] == "READ"
        and key not in allowed_reads
        and writes.search(inspect.getsource(route.endpoint))
    ]
    assert offenders == [], f"GET routes that write must not be READ: {offenders}"


def test_exports_and_administration_are_sensitive():
    for key, klass in ROUTE_POLICY.items():
        _method, path = key.split(" ", 1)
        if path.endswith("/export") or "/admin/" in path:
            assert klass == "SENSITIVE", key
    for key in (
        "PUT /api/atwork/management/settings",
        "GET /api/atwork/management/audit",
        "POST /api/atwork/management/corrections/{request_id}/approve",
    ):
        assert ROUTE_POLICY[key] == "SENSITIVE", key
    assert ROUTE_POLICY["POST /api/atwork/attendance/check-in"] == "OWN"


def test_routes_marked_exempt_really_do_not_authenticate_a_user(api_client, db, monkeypatch):
    seen = []
    real = fastapi_deps.route_class
    monkeypatch.setattr(fastapi_deps, "route_class", lambda method, path: seen.append(f"{method} {path}") or real(method, path))
    _guard({})
    for method, path in _routes_requiring_a_token(api_client):
        api_client.request(method, path, headers=_staff_headers(av=0))
    exempt_but_authenticating = [k for k in seen if ROUTE_POLICY.get(k) == "EXEMPT"]
    assert exempt_but_authenticating == []
    unclassified = [k for k in seen if k not in ROUTE_POLICY]
    assert unclassified == [], f"the guard met routes with no policy entry: {unclassified}"


# --- behaviour through the real routes ---------------------------------------------------


def test_a_revoked_session_is_refused_by_every_authenticated_route(api_client, db):
    routes = _routes_requiring_a_token(api_client)
    _guard({USER_ID: (3, True)})
    marked = 0
    for method, path in routes:
        resp = api_client.request(method, path, headers=_staff_headers(av=1))
        assert resp.status_code == 401, f"{method} {path}: {resp.status_code}"
        marked += resp.headers.get("x-auth-error") == "session_revoked"
    assert marked >= 10, f"only {marked} of {len(routes)} routes reported a revoked session"


def test_an_inactive_account_is_refused_whatever_its_version(api_client, db):
    _guard({USER_ID: (0, False)})
    routes = [r for r in _routes_requiring_a_token(api_client) if r[0] == "GET"]
    refused = [
        r
        for r in routes
        if api_client.request(*r, headers=_staff_headers(av=50)).headers.get("x-auth-error") == "session_revoked"
    ]
    assert len(refused) >= 1


def test_a_replica_with_no_snapshot_serves_only_read_and_own_routes(api_client, db):
    routes = _routes_requiring_a_token(api_client)
    _guard({}, loaded=False)  # a cold start that could not reach platform-api
    refused_flags = {"revocation_restricted", "revocation_stale"}
    served_kinds = {"READ", "OWN", "EXEMPT"}
    refused = served = 0
    for method, path in routes:
        key = next((k for k in ROUTE_POLICY if k.split(" ", 1)[0] == method and _matches(k.split(" ", 1)[1], path)), None)
        resp = api_client.request(method, path, headers=_staff_headers(av=0))
        flag = resp.headers.get("x-auth-error")
        if key is None:
            continue
        if ROUTE_POLICY[key] in served_kinds:
            assert flag not in refused_flags, f"{key} is {ROUTE_POLICY[key]} yet was refused"
            served += 1
        else:
            assert flag in refused_flags, f"{key} is {ROUTE_POLICY[key]} yet was served with no snapshot"
            refused += 1
    assert refused >= 1 and served >= 1


def _matches(template, concrete):
    return re.fullmatch(re.sub(r"\{[^}]+\}", "[^/]+", template), concrete) is not None


def test_everything_a_manager_sees_about_others_is_sensitive_except_the_access_probe():
    for key, klass in ROUTE_POLICY.items():
        _method, path = key.split(" ", 1)
        if path.startswith("/api/atwork/management") and not path.endswith("/management/access"):
            assert klass == "SENSITIVE", key
    assert ROUTE_POLICY["GET /api/atwork/management/access"] == "READ"


# --- View-as: a read-only simulation of another employee ---------------------------------------


def _view_as_headers():
    now = datetime.now(UTC)
    body = {
        "sub": str(USER_ID),
        "iat": now,
        "exp": now + timedelta(minutes=30),
        "iss": "dijione-dev-identity",
        "is_active": True,
        "full_name": "Employee",
        "email": "employee@example.com",
        "av": 0,
        "platform_role": "PLATFORM_USER",
        "platform_permissions": [],
        "module_roles": {},
        "actor_type": "view_as",
        "view_as": {"session_id": "S-1", "actor_id": 99, "actor_name": "Admin", "actor_av": 0},
    }
    return {"Authorization": "Bearer " + jwt.encode(body, SECRET, algorithm="HS256")}


def test_a_view_as_session_can_reach_only_read_routes_of_this_service(api_client, db):
    """Every route that authenticates a user: a View-as token is refused unless the route is a GET
    classified READ. The employee in the token has no module access, so a READ route may answer
    403/404 for that reason, but never with the read-only refusal."""
    routes = _routes_requiring_a_token(api_client)
    assert routes
    refused = admitted = 0
    for method, path in routes:
        resp = api_client.request(method, path, headers=_view_as_headers())
        key = next((k for k in ROUTE_POLICY if k.split(" ", 1)[0] == method and _matches(k.split(" ", 1)[1], path)), None)
        flag = resp.headers.get("x-auth-error")
        if key is not None and method == "GET" and ROUTE_POLICY[key] in ("READ", "EXEMPT"):
            assert flag != "view_as_read_only", f"{key} is READ yet a View-as session was refused"
            admitted += 1
        elif key is not None and ROUTE_POLICY[key] != "EXEMPT":  # EXEMPT routes authenticate no user
            assert resp.status_code == 403 and flag == "view_as_read_only", f"{key}: {resp.status_code} {flag}"
            refused += 1
    assert refused >= 1 and admitted >= 0


def test_no_route_of_this_service_is_ever_open_to_a_view_as_session_for_changes(api_client, db):
    for key, klass in ROUTE_POLICY.items():
        method = key.split(" ", 1)[0]
        if method != "GET":
            assert klass != "READ", key  # a change is never READ, so a View-as session can never make one
