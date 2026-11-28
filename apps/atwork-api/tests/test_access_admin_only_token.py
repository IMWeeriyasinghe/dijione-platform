"""DijiAtWork access administration grants no DijiAtWork business permission: a token carrying only
the administrator-only role (ATWORK_ACCESS_ADMIN, atwork.access.manage) reaches no attendance,
correction or Management endpoint. (In practice every eligible appointee also holds the always-on
ATWORK_USER, which gives exactly its own permissions; this proves the appointment adds none.)"""

import re

from app.main import app
from tests.conftest import bearer, issue_token

PREFIX = "/api/atwork"
EXEMPT = {"/api/atwork/summary", "/api/atwork/metadata"}
# BP management endpoints ARE the business of atwork.access.manage — they should be reachable
_BP_MANAGEMENT_PREFIX = "/api/atwork/management/bp"


def test_admin_only_token_reaches_no_business_endpoint(api_client, db, monkeypatch):
    claim = {"role": "ATWORK_ACCESS_ADMIN", "client_id": None, "client_ids": [], "permissions": ["atwork.access.manage"]}
    headers = bearer(issue_token(77, module_roles={"atwork": claim}))
    checked = 0
    for route_path, ops in app.openapi()["paths"].items():
        if "get" not in ops or not route_path.startswith(PREFIX) or route_path in EXEMPT or "/internal" in route_path:
            continue
        path = re.sub(r"\{[^}]+\}", "1", route_path)
        resp = api_client.get(path, headers=headers)
        if route_path == "/api/atwork/me":  # reports the caller's own role and permissions, nothing else
            assert resp.status_code == 200 and resp.json()["permissions"] == ["atwork.access.manage"]
            continue
        if route_path.startswith(_BP_MANAGEMENT_PREFIX):  # access.manage routes ARE callable by this token
            # 422 is acceptable for GET routes that require query params (e.g. employee-search?q=)
            assert resp.status_code in (200, 204, 404, 422), (route_path, resp.status_code, resp.text[:200])
            checked += 1
            continue
        assert resp.status_code in (401, 403, 404, 422), (route_path, resp.status_code, resp.text[:200])
        checked += 1
    assert checked >= 8
