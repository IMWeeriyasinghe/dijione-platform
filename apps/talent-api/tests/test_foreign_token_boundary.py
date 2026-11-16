"""Authentication boundary: DijiTalentFlow must not treat a token signed for another
actor population as one of its users.

Supplier-portal sessions (DijiBirthday) share the platform signing secret and
issuer, so they pass signature and issuer checks here. They must still reach
no DijiTalentFlow data."""

import os
import re
from datetime import UTC, datetime, timedelta

from jose import jwt

from app.main import app

SECRET = os.environ["PLATFORM_JWT_SECRET"]
DENIED = (401, 403)
# Returns only what the caller's own token says; reads no application data.
IDENTITY_ECHO = set()


def _bearer(payload, *, secret=SECRET, issuer="dijione-dev-identity"):
    now = datetime.now(UTC)
    body = {"iat": now, "exp": now + timedelta(hours=1), "iss": issuer, "is_active": True, **payload}
    return {"Authorization": "Bearer " + jwt.encode(body, secret, algorithm="HS256")}


def _supplier_session(sub=1, **supplier):
    """The shape birthday-api signs for a supplier-portal user."""
    portal = {"role": "BIRTHDAY_SUPPLIER", "client_id": None, "client_ids": None,
              "permissions": ["birthday.portal.access", "birthday.portal.respond"]}
    return _bearer({
        "sub": str(sub), "full_name": "Supplier Person", "email": "orders@supplier.example",
        "platform_role": "PLATFORM_USER", "platform_permissions": [], "module_roles": {"birthday": portal},
        "supplier": {"supplier_id": 5, "supplier_user_id": sub, **supplier},
    })


def _routes_requiring_a_token(api_client):
    """Every route that answers 401 to a request without a token."""
    found = []
    for raw_path, operations in app.openapi()["paths"].items():
        path = re.sub(r"\{[^}]+\}", "1", raw_path)
        for method in sorted(m.upper() for m in operations):
            if api_client.request(method, path).status_code == 401:
                found.append((method, path))
    return found


def test_supplier_portal_tokens_reach_no_protected_route(api_client, db):
    routes = [r for r in _routes_requiring_a_token(api_client) if r not in IDENTITY_ECHO]
    assert len(routes) >= 40, routes
    tokens = {
        "supplier session": _supplier_session(),
        "supplier read-only impersonation": _supplier_session(read_only=True, impersonated_by=1),
    }
    for label, headers in tokens.items():
        for method, path in routes:
            status = api_client.request(method, path, headers=headers).status_code
            assert status in DENIED, f"{label} was accepted on {method} {path}: {status}"


def test_tokens_from_other_issuers_or_signers_are_not_authenticated(api_client, db):
    roles = {"talent-flow": {"role": "TA_MANAGER", "permissions": ["talent.workspace.staff"]}}
    staff = {"sub": "1", "full_name": "Staff", "email": "staff@example.com", "module_roles": roles}
    wrong = {
        "sign-in flow issuer": _bearer(staff, issuer="dijione-entra-flow"),
        "supplier sign-in flow issuer": _bearer(staff, issuer="dijibirthday-supplier-entra-flow"),
        "another signing secret": _bearer(staff, secret="a-different-secret"),
    }
    routes = [r for r in _routes_requiring_a_token(api_client)]
    for label, headers in wrong.items():
        for method, path in routes:
            status = api_client.request(method, path, headers=headers).status_code
            assert status == 401, f"{label} was authenticated on {method} {path}: {status}"
