"""Authentication boundary between DijiBirthday staff and supplier-portal users.

Both kinds of token are signed with the platform secret and issuer, so the only
thing separating them is what each route requires. A real supplier session must
reach no staff route, and a staff session must reach no supplier-portal route."""

import re

from app.main import app
from app.services.supplier_auth import mint_supplier_session_token
from tests.conftest import headers_for

DENIED = (401, 403)
PORTAL = "/api/birthday/portal"
# Returns only the caller's own id and name from their token.
IDENTITY_ECHO = {("GET", "/api/birthday/whoami")}


def _supplier_user(db):
    from app.models.supplier import Supplier
    from app.models.supplier_user import SupplierUser

    supplier = Supplier(name="Boundary Bakery", primary_contact_email="b@bakery.example.com")
    db.add(supplier)
    db.commit()
    user = SupplierUser(supplier_id=supplier.id, email="u@bakery.example.com", full_name="Boundary User", status="ACTIVE")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _routes_requiring_a_token(api_client):
    found = []
    for raw_path, operations in app.openapi()["paths"].items():
        path = re.sub(r"\{[^}]+\}", "1", raw_path)
        for method in sorted(m.upper() for m in operations):
            if api_client.request(method, path).status_code == 401:
                found.append((method, path))
    return found


def test_supplier_sessions_reach_no_staff_route(api_client, db):
    user = _supplier_user(db)
    tokens = {
        "supplier session": _bearer(mint_supplier_session_token(user)),
        "read-only impersonation": _bearer(mint_supplier_session_token(user, read_only=True, impersonated_by=1)),
    }
    staff_routes = [
        r for r in _routes_requiring_a_token(api_client) if not r[1].startswith(PORTAL) and r not in IDENTITY_ECHO
    ]
    assert len(staff_routes) >= 45, staff_routes
    for label, headers in tokens.items():
        assert api_client.get(f"{PORTAL}/me", headers=headers).status_code == 200  # a genuine, working session
        for method, path in staff_routes:
            status = api_client.request(method, path, headers=headers).status_code
            assert status in DENIED, f"{label} was accepted on staff route {method} {path}: {status}"


def test_staff_sessions_reach_no_supplier_portal_route(api_client, db):
    _supplier_user(db)  # a supplier user whose id equals the staff user's id below
    portal_routes = [r for r in _routes_requiring_a_token(api_client) if r[1].startswith(PORTAL)]
    assert len(portal_routes) >= 10, portal_routes
    for role in ("BIRTHDAY_ADMIN", "BIRTHDAY_USER", "BIRTHDAY_SUPPLIER", None):
        headers = headers_for(1, role=role)
        for method, path in portal_routes:
            status = api_client.request(method, path, headers=headers).status_code
            assert status in DENIED, f"staff {role} was accepted on portal route {method} {path}: {status}"


def test_read_only_impersonation_cannot_write_anywhere(api_client, db):
    user = _supplier_user(db)
    headers = _bearer(mint_supplier_session_token(user, read_only=True, impersonated_by=1))
    writes = [r for r in _routes_requiring_a_token(api_client) if r[0] != "GET" and r not in IDENTITY_ECHO]
    assert len(writes) >= 30, writes
    for method, path in writes:
        status = api_client.request(method, path, headers=headers).status_code
        assert status in DENIED, f"read-only impersonation was accepted on {method} {path}: {status}"
