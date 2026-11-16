"""Platform Core must accept a token as a user session only when it is that
DijiOne user's own staff session.

Supplier-portal tokens (DijiBirthday) are signed with the same secret and
issuer, and their numeric ``sub`` is a supplier-user id. Read as a DijiOne
user id it selects an unrelated account, possibly an administrator."""

import os
from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt

from app.core.security import decode_session_token
from tests.conftest import auth_headers

SECRET = os.environ["PLATFORM_JWT_SECRET"]

# Every route that authenticates a user, read and write.
USER_ROUTES = [
    ("get", "/api/auth/me"),
    ("get", "/api/modules"),
    ("get", "/api/notifications"),
    ("post", "/api/notifications/1/read"),
    ("get", "/api/platform/admin/dashboard"),
    ("get", "/api/platform/admin/users"),
    ("get", "/api/platform/admin/audit"),
    ("patch", "/api/platform/admin/users/1/status"),
    ("patch", "/api/platform/admin/users/1/platform-role"),
    ("put", "/api/platform/admin/users/1/modules/talent-flow"),
    ("delete", "/api/platform/admin/users/1/modules/talent-flow"),
    ("post", "/api/platform/admin/groups"),
]


def _signed(payload, *, secret=SECRET, issuer="dijione-dev-identity"):
    now = datetime.now(UTC)
    body = {"iat": now, "exp": now + timedelta(hours=1), "iss": issuer, **payload}
    return {"Authorization": "Bearer " + jwt.encode(body, secret, algorithm="HS256")}


def _supplier_token(sub, **supplier):
    """The shape birthday-api signs for a supplier-portal user."""
    return _signed({
        "sub": str(sub), "is_active": True, "full_name": "Supplier Person", "email": "orders@supplier.example",
        "platform_role": "PLATFORM_USER", "platform_permissions": [],
        "module_roles": {"birthday": {"role": "BIRTHDAY_SUPPLIER", "client_id": None, "client_ids": None,
                                      "permissions": ["birthday.portal.access", "birthday.portal.respond"]}},
        "supplier": {"supplier_id": 5, "supplier_user_id": sub, **supplier},
    })


def _foreign_tokens(admin):
    """Tokens of other actor populations whose ``sub`` equals an administrator's id."""
    return {
        "supplier session": _supplier_token(admin.id),
        "supplier read-only impersonation": _supplier_token(admin.id, read_only=True, impersonated_by=admin.id),
        "external client link": _signed({"sub": str(admin.id), "email": admin.email, "external": {"grant_id": 9}}),
        "declared non-staff actor": _signed({"sub": str(admin.id), "email": admin.email, "actor_type": "supplier"}),
        "same number, other person's email": _signed({"sub": str(admin.id), "email": "orders@supplier.example"}),
        "same number, no email": _signed({"sub": str(admin.id)}),
        "staff marker, other person's email": _signed(
            {"sub": str(admin.id), "email": "orders@supplier.example", "actor_type": "staff"}
        ),
    }


@pytest.mark.parametrize(("method", "path"), USER_ROUTES)
def test_tokens_of_other_actor_populations_are_never_a_user_session(api_client, db, two_tenant_world, method, path):
    for label, headers in _foreign_tokens(two_tenant_world["super_admin"]).items():
        resp = getattr(api_client, method)(path, headers=headers)
        assert resp.status_code == 401, f"{label} was accepted on {method.upper()} {path}: {resp.status_code}"


def test_rejected_token_changes_nothing(api_client, db, two_tenant_world):
    from app.models.audit_log import AuditLog
    from app.models.user import User

    admin, target = two_tenant_world["super_admin"], two_tenant_world["ta_user"]
    headers = _supplier_token(admin.id)
    base = f"/api/platform/admin/users/{target.id}"
    api_client.patch(f"{base}/platform-role", json={"platform_role": "SUPER_ADMIN"}, headers=headers)
    api_client.patch(f"{base}/status", json={"is_active": False}, headers=headers)
    db.expire_all()
    refreshed = db.get(User, target.id)
    assert (refreshed.platform_role, refreshed.is_active) == ("PLATFORM_USER", True)
    assert db.query(AuditLog).count() == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"sub": "not-a-number", "email": "x@example.com"},
        {"email": "x@example.com"},
        {"sub": None, "email": "x@example.com"},
    ],
)
def test_malformed_subject_is_unauthorised_not_an_error(api_client, db, two_tenant_world, payload):
    assert api_client.get("/api/auth/me", headers=_signed(payload)).status_code == 401


def test_tokens_for_other_purposes_or_from_other_signers_are_rejected(api_client, db, two_tenant_world):
    admin = two_tenant_world["super_admin"]
    staff = {"sub": str(admin.id), "email": admin.email, "actor_type": "staff"}
    wrong = {
        "sign-in flow token": _signed(staff, issuer="dijione-entra-flow"),
        "supplier sign-in flow token": _signed(staff, issuer="dijibirthday-supplier-entra-flow"),
        "external-session issuer": _signed(staff, issuer="dijitalent-external"),
        "another signing secret": _signed(staff, secret="a-different-secret"),
        "expired": _signed({**staff, "exp": datetime.now(UTC) - timedelta(minutes=1)}),
    }
    for label, headers in wrong.items():
        assert api_client.get("/api/platform/admin/users", headers=headers).status_code == 401, label


def test_issued_sessions_are_marked_staff_and_work(api_client, db, two_tenant_world):
    for persona, admin_status in (("test-super-admin", 200), ("test-platform-admin", 200), ("test-ta", 403)):
        headers = auth_headers(api_client, persona)
        claims = decode_session_token(headers["Authorization"].split()[1])
        assert claims["actor_type"] == "staff"
        assert api_client.get("/api/auth/me", headers=headers).status_code == 200
        assert api_client.get("/api/modules", headers=headers).status_code == 200
        assert api_client.get("/api/platform/admin/users", headers=headers).status_code == admin_status


def test_session_issued_before_the_marker_existed_still_works_until_it_expires(api_client, db, two_tenant_world):
    """Users signed in when the fix is deployed are not signed out."""
    admin = two_tenant_world["super_admin"]
    legacy = _signed({"sub": str(admin.id), "email": admin.email.upper(), "is_active": True, "platform_role": "SUPER_ADMIN"})
    assert api_client.get("/api/platform/admin/users", headers=legacy).status_code == 200


def test_deactivated_user_session_is_rejected(api_client, db, two_tenant_world):
    headers = auth_headers(api_client, "test-ta")
    two_tenant_world["ta_user"].is_active = False
    db.commit()
    assert api_client.get("/api/auth/me", headers=headers).status_code == 401
