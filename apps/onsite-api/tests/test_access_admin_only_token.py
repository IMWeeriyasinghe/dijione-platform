"""An appointed Diji On-site access administrator with no business role (role ONSITE_ACCESS_ADMIN,
permission onsite.access.manage) reaches no On-site business endpoint. Every GET route is swept, so a
new route is covered automatically."""

import os
import re
from datetime import UTC, datetime, timedelta

from jose import jwt

from app.main import app

PREFIX = "/api/onsite"
EXEMPT = {"/api/onsite/summary", "/api/onsite/metadata"}


def _admin_only_headers():
    now = datetime.now(UTC)
    claim = {"role": "ONSITE_ACCESS_ADMIN", "client_id": None, "client_ids": [], "permissions": ["onsite.access.manage"]}
    payload = {"sub": "77", "iat": now, "exp": now + timedelta(minutes=5), "iss": "dijione-dev-identity",
               "is_active": True, "full_name": "Tom", "email": "tom@example.com", "platform_role": "PLATFORM_USER",
               "platform_permissions": [], "module_roles": {"onsite": claim}, "actor_type": "staff"}
    return {"Authorization": "Bearer " + jwt.encode(payload, os.environ["PLATFORM_JWT_SECRET"], algorithm="HS256")}


def test_admin_only_token_reaches_no_business_endpoint(api_client, db):
    headers = _admin_only_headers()
    checked = 0
    for route_path, ops in app.openapi()["paths"].items():
        if "get" not in ops or not route_path.startswith(PREFIX) or route_path in EXEMPT or "/internal" in route_path:
            continue
        path = re.sub(r"\{[^}]+\}", "1", route_path)
        resp = api_client.get(path, headers=headers)
        if route_path == "/api/onsite/me":  # reports the caller's own role and permissions, nothing else
            assert resp.status_code == 200 and resp.json()["permissions"] == ["onsite.access.manage"]
            continue
        assert resp.status_code in (401, 403, 404, 422), (route_path, resp.status_code, resp.text[:200])
        checked += 1
    assert checked >= 8
