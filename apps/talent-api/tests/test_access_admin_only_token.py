"""An appointed access administrator with no business role holds a DijiTalentFlow entry in the
session token (role TALENT_ACCESS_ADMIN, permission talent.access.manage, no clients). It opens the
application's Access page, which is served by Platform Core; every DijiTalentFlow business endpoint
must refuse it. Every GET route is swept, so a new route is covered automatically."""

import os
import re
from datetime import UTC, datetime, timedelta

from jose import jwt

from app.main import app

PREFIX = "/api/talent"
EXEMPT = {"/api/talent/summary", "/api/talent/metadata"}  # unauthenticated aggregate/status by design


def _admin_only_headers():
    now = datetime.now(UTC)
    claim = {"role": "TALENT_ACCESS_ADMIN", "client_id": None, "client_ids": [], "client_public_id": None,
             "client_public_ids": [], "permissions": ["talent.access.manage"]}
    payload = {"sub": "77", "iat": now, "exp": now + timedelta(minutes=5), "iss": "dijione-dev-identity",
               "is_active": True, "full_name": "Tom", "email": "tom@example.com", "platform_role": "PLATFORM_USER",
               "platform_permissions": [], "module_roles": {"talent-flow": claim}, "actor_type": "staff"}
    return {"Authorization": "Bearer " + jwt.encode(payload, os.environ["PLATFORM_JWT_SECRET"], algorithm="HS256")}


def test_admin_only_token_reaches_no_business_endpoint(api_client, db):
    headers = _admin_only_headers()
    checked = 0
    for route_path, ops in app.openapi()["paths"].items():
        if "get" not in ops or not route_path.startswith(PREFIX):
            continue
        if route_path in EXEMPT or "/internal" in route_path or "/external" in route_path:
            continue  # internal: service secret only; external: magic-link sessions, a separate population
        path = re.sub(r"\{[^}]+\}", "1", route_path)
        resp = api_client.get(path, headers=headers)
        assert resp.status_code in (401, 403, 404, 422), (route_path, resp.status_code, resp.text[:200])
        checked += 1
    assert checked >= 10
    assert api_client.post("/api/talent/requests/1/messages", headers=headers, json={"body": "x"}).status_code in (403, 404, 422)
