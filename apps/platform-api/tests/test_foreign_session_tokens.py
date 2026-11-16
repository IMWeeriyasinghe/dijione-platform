"""Supplier-portal and external-link sessions are signed for other actor
populations. Platform Core must never read their ``sub`` as a DijiOne user id."""

import os
from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt


def _token(sub, **extra):
    now = datetime.now(UTC)
    payload = {
        "sub": str(sub), "iat": now, "exp": now + timedelta(hours=1), "iss": "dijione-dev-identity",
        "is_active": True, "platform_role": "PLATFORM_USER", "platform_permissions": [],
        "module_roles": {"birthday": {"role": "BIRTHDAY_SUPPLIER", "permissions": ["birthday.portal.access"]}},
        **extra,
    }
    return {"Authorization": "Bearer " + jwt.encode(payload, os.environ["PLATFORM_JWT_SECRET"], algorithm="HS256")}


@pytest.mark.parametrize(
    "extra",
    [
        {"supplier": {"supplier_id": 5, "supplier_user_id": 1}},
        {"supplier": {"supplier_id": 5, "supplier_user_id": 1, "read_only": True, "impersonated_by": 2}},
        {"external": {"grant_id": 9}},
    ],
)
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/auth/me"),
        ("post", "/api/auth/refresh"),
        ("get", "/api/modules"),
        ("get", "/api/notifications"),
        ("get", "/api/platform/admin/users"),
        ("get", "/api/platform/admin/audit"),
    ],
)
def test_token_for_another_actor_population_is_rejected(api_client, db, two_tenant_world, extra, method, path):
    # The token's numeric id deliberately equals a SUPER_ADMIN's user id.
    headers = _token(two_tenant_world["super_admin"].id, **extra)
    assert getattr(api_client, method)(path, headers=headers).status_code == 401


def test_ordinary_session_token_is_unaffected(api_client, db, two_tenant_world):
    headers = _token(two_tenant_world["super_admin"].id)
    assert api_client.get("/api/platform/admin/users", headers=headers).status_code == 200
