"""D2: a signed-in user picks up grants and revocations by refreshing the
session token, without signing in again and without extending the sign-in."""

import os
from datetime import UTC, datetime, timedelta

from jose import jwt

from app.core.config import get_settings
from app.core.security import decode_session_token
from app.models.user import User
from tests.conftest import auth_headers

MODULE = "talent-flow"
ALL_CLIENTS = {"all_clients": True, "client_ids": []}


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _refresh(api_client, headers):
    return api_client.post("/api/auth/refresh", headers=headers)


def _forge(user, **claims):
    """A correctly signed session token with chosen timestamps. Like every real
    session it names the user's email, which the platform checks against the account."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id), "email": user.email, "iat": now, "exp": now + timedelta(minutes=5),
        "iss": "dijione-dev-identity", "actor_type": "staff", **claims,
    }
    return jwt.encode(payload, os.environ["PLATFORM_JWT_SECRET"], algorithm="HS256")


def _newcomer(db):
    user = User(email="newcomer@example.com", full_name="Newcomer", persona_key="test-newcomer")
    db.add(user)
    db.commit()
    return user


def test_grant_reaches_a_signed_in_user_on_refresh(api_client, db, two_tenant_world):
    user = _newcomer(db)
    session = auth_headers(api_client, "test-newcomer")
    assert decode_session_token(session["Authorization"].split()[1])["module_roles"] == {}

    admin = auth_headers(api_client, "test-platform-admin")
    assert api_client.put(
        f"/api/platform/admin/users/{user.id}/modules/{MODULE}",
        json={"role": "TA_MEMBER", "enabled": True, "client_scope": ALL_CLIENTS}, headers=admin,
    ).status_code == 200

    resp = _refresh(api_client, session)
    assert resp.status_code == 200
    claims = decode_session_token(resp.json()["access_token"])
    assert claims["module_roles"][MODULE]["role"] == "TA_MEMBER"
    assert "talent.requests.read" in claims["module_roles"][MODULE]["permissions"]
    assert [r["module_key"] for r in resp.json()["user"]["module_roles"]] == [MODULE]


def test_revocation_and_role_change_reach_a_signed_in_user_on_refresh(api_client, db, two_tenant_world):
    session = auth_headers(api_client, "test-cs")
    admin = auth_headers(api_client, "test-platform-admin")
    url = f"/api/platform/admin/users/{two_tenant_world['cs_user'].id}/modules/{MODULE}"

    api_client.put(url, json={"role": "TA_MEMBER", "enabled": True}, headers=admin)
    changed = decode_session_token(_refresh(api_client, session).json()["access_token"])["module_roles"][MODULE]
    assert changed["role"] == "TA_MEMBER"
    assert "talent.requests.review" not in changed["permissions"]

    assert api_client.delete(url, headers=admin).status_code == 200
    resp = _refresh(api_client, session)
    assert decode_session_token(resp.json()["access_token"])["module_roles"] == {}
    assert resp.json()["user"]["module_roles"] == []


def test_deactivated_user_cannot_refresh(api_client, db, two_tenant_world):
    session = auth_headers(api_client, "test-ta")
    admin = auth_headers(api_client, "test-platform-admin")
    api_client.patch(
        f"/api/platform/admin/users/{two_tenant_world['ta_user'].id}/status", json={"is_active": False}, headers=admin
    )
    assert _refresh(api_client, session).status_code == 401


def test_refresh_keeps_the_original_sign_in_time_and_never_outlives_the_session(api_client, db, two_tenant_world, monkeypatch):
    user = two_tenant_world["ta_user"]
    started = datetime.now(UTC) - timedelta(minutes=700)  # 20 minutes of a 12 hour session left
    resp = _refresh(api_client, _bearer(_forge(user, sst=int(started.timestamp()))))
    assert resp.status_code == 200
    claims = decode_session_token(resp.json()["access_token"])
    assert claims["sst"] == int(started.timestamp())
    assert claims["exp"] == int(started.timestamp()) + 720 * 60

    # A short token lifetime shortens each token, not the session.
    monkeypatch.setenv("JWT_EXPIRES_MINUTES", "15")
    get_settings.cache_clear()
    try:
        short = decode_session_token(_refresh(api_client, auth_headers(api_client, "test-ta")).json()["access_token"])
        assert 14 * 60 <= short["exp"] - short["iat"] <= 15 * 60
    finally:
        monkeypatch.delenv("JWT_EXPIRES_MINUTES")
        get_settings.cache_clear()


def test_refresh_is_refused_once_the_session_limit_is_reached(api_client, db, two_tenant_world):
    user = two_tenant_world["ta_user"]
    started = datetime.now(UTC) - timedelta(minutes=721)
    resp = _refresh(api_client, _bearer(_forge(user, sst=int(started.timestamp()))))
    assert resp.status_code == 401
    assert "sign in again" in resp.json()["detail"]


def test_token_issued_before_this_change_refreshes_from_its_issue_time(api_client, db, two_tenant_world):
    user = two_tenant_world["ta_user"]
    issued = datetime.now(UTC) - timedelta(hours=3)
    resp = _refresh(api_client, _bearer(_forge(user, iat=issued)))
    assert resp.status_code == 200
    assert decode_session_token(resp.json()["access_token"])["sst"] == int(issued.timestamp())


def test_refresh_needs_a_valid_token_and_is_not_a_sign_in(api_client, db, two_tenant_world):
    assert _refresh(api_client, {}).status_code == 401
    assert _refresh(api_client, _bearer("garbage")).status_code == 401
    expired = _forge(two_tenant_world["ta_user"], exp=datetime.now(UTC) - timedelta(minutes=1))
    assert _refresh(api_client, _bearer(expired)).status_code == 401

    session = auth_headers(api_client, "test-ta")
    db.expire_all()
    before = db.get(User, two_tenant_world["ta_user"].id).last_login_at
    assert _refresh(api_client, session).status_code == 200
    db.expire_all()
    assert db.get(User, two_tenant_world["ta_user"].id).last_login_at == before
