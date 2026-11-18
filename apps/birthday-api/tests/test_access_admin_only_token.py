"""An appointed DIJI Birthday access administrator with no business role (role
BIRTHDAY_ACCESS_ADMIN, permission birthday.access.manage) reaches no Birthday business endpoint.
Every GET route is swept, so a new route is covered automatically."""

import os
import re
from datetime import UTC, datetime, timedelta

from jose import jwt

from app.main import app

PREFIX = "/api/birthday"
EXEMPT = {"/api/birthday/summary", "/api/birthday/metadata", "/api/birthday/meta"}


def _admin_only_headers():
    now = datetime.now(UTC)
    claim = {"role": "BIRTHDAY_ACCESS_ADMIN", "client_id": None, "client_ids": [], "permissions": ["birthday.access.manage"]}
    payload = {"sub": "77", "iat": now, "exp": now + timedelta(minutes=5), "iss": "dijione-dev-identity",
               "is_active": True, "full_name": "Tom", "email": "tom@example.com", "platform_role": "PLATFORM_USER",
               "platform_permissions": [], "module_roles": {"birthday": claim}, "actor_type": "staff"}
    return {"Authorization": "Bearer " + jwt.encode(payload, os.environ["PLATFORM_JWT_SECRET"], algorithm="HS256")}


def test_admin_only_token_reaches_no_business_endpoint(api_client, db):
    headers = _admin_only_headers()
    checked = 0
    for route_path, ops in app.openapi()["paths"].items():
        if "get" not in ops or not route_path.startswith(PREFIX) or route_path in EXEMPT:
            continue
        if "/internal" in route_path or "/supplier/auth" in route_path:
            continue  # service secret only; supplier sign-in (another actor population)
        path = re.sub(r"\{[^}]+\}", "1", route_path)
        resp = api_client.get(path, headers=headers)
        if route_path == "/api/birthday/whoami":  # echoes the caller's own identity only
            assert resp.json() == {"user_id": 77, "full_name": "Tom"}
            continue
        assert resp.status_code in (401, 403, 404, 422), (route_path, resp.status_code, resp.text[:200])
        checked += 1
    assert checked >= 10
