"""Microsoft Entra ID SSO backend flow.

Entra's JWKS fetch and the authorization-code exchange are mocked — no
network. Entra authenticates; DijiOne still issues its own session token, so
the returned access_token is verifiable with the local dev secret exactly
like a dev-login token.
"""

from urllib.parse import parse_qs, urlparse

import pytest
from jose import jwt

from app.core.config import get_settings
from app.core.security import get_entra_verifier
from app.models.user import User

ENTRA_ENV = {
    "AUTH_MODE": "entra",
    "ENTRA_TENANT_ID": "test-tenant",
    "ENTRA_CLIENT_ID": "test-client",
    "ENTRA_CLIENT_SECRET": "test-secret",
    "ENTRA_REDIRECT_URI": "http://localhost:3000/api/auth/callback",
}


@pytest.fixture()
def entra_mode(monkeypatch):
    for k, v in ENTRA_ENV.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    get_entra_verifier.cache_clear()
    yield
    get_settings.cache_clear()
    get_entra_verifier.cache_clear()


def _mock_code_exchange(monkeypatch, *, id_token="fake.id.token", ok=True):
    class _Resp:
        status_code = 200 if ok else 400

        def json(self):
            return {"id_token": id_token} if ok else {"error": "invalid_grant"}

    monkeypatch.setattr("app.api.routes.auth_entra.httpx.post", lambda *a, **k: _Resp())


def _mock_verify(monkeypatch, claims):
    monkeypatch.setattr(
        "app.core.security.EntraTokenVerifier.verify_id_token",
        lambda self, id_token, nonce=None: claims,
    )


def _login_url(api_client):
    resp = api_client.get("/api/auth/entra/login-url")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    state = parse_qs(urlparse(body["authorize_url"]).query)["state"][0]
    return body["flow_token"], state


# --- mode gating -----------------------------------------------------------

def test_dev_mode_disables_entra_endpoints(api_client, db):
    assert api_client.get("/api/auth/entra/login-url").status_code == 501
    assert api_client.get("/api/auth/config").json() == {"auth_mode": "dev"}
    assert api_client.get("/api/auth/dev-personas").status_code == 200


def test_entra_mode_disables_dev_endpoints(api_client, db, entra_mode):
    assert api_client.get("/api/auth/config").json() == {"auth_mode": "entra"}
    assert api_client.get("/api/auth/dev-personas").status_code == 404
    assert api_client.post("/api/auth/dev-login", json={"persona_key": "x"}).status_code == 404
    assert api_client.get("/api/auth/entra/login-url").status_code == 200


def test_entra_mode_missing_config_501(api_client, db, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "entra")  # but no ENTRA_* values
    get_settings.cache_clear()
    try:
        assert api_client.get("/api/auth/entra/login-url").status_code == 501
    finally:
        get_settings.cache_clear()


# --- token exchange ------------------------------------------------------

def test_token_exchange_issues_dijione_session_for_known_user(api_client, db, entra_mode, monkeypatch):
    db.add(User(email="known@example.com", full_name="Known", platform_role="PLATFORM_USER",
                persona_key="k", is_active=True))
    db.commit()

    flow_token, state = _login_url(api_client)
    _mock_code_exchange(monkeypatch)
    _mock_verify(monkeypatch, {"oid": "oid-1", "email": "known@example.com", "name": "Known", "tid": "test-tenant"})

    resp = api_client.post(
        "/api/auth/entra/token",
        json={"code": "abc", "state": state, "flow_token": flow_token},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    decoded = jwt.decode(token, "test-only-secret", algorithms=["HS256"], issuer="dijione-dev-identity")
    assert decoded["email"] == "known@example.com"

    user = db.query(User).filter_by(email="known@example.com").one()
    assert user.entra_object_id == "oid-1"
    assert user.identity_provider == "ENTRA"


def test_token_exchange_state_mismatch_400(api_client, db, entra_mode, monkeypatch):
    flow_token, _state = _login_url(api_client)
    _mock_code_exchange(monkeypatch)
    resp = api_client.post(
        "/api/auth/entra/token",
        json={"code": "abc", "state": "WRONG", "flow_token": flow_token},
    )
    assert resp.status_code == 400


def test_token_exchange_bad_id_token_401(api_client, db, entra_mode, monkeypatch):
    from app.core.security import InvalidTokenError

    flow_token, state = _login_url(api_client)
    _mock_code_exchange(monkeypatch)
    monkeypatch.setattr(
        "app.core.security.EntraTokenVerifier.verify_id_token",
        lambda self, id_token, nonce=None: (_ for _ in ()).throw(InvalidTokenError("bad sig")),
    )
    resp = api_client.post(
        "/api/auth/entra/token",
        json={"code": "abc", "state": state, "flow_token": flow_token},
    )
    assert resp.status_code == 401


def test_token_exchange_unknown_user_is_created_inactive_403(api_client, db, entra_mode, monkeypatch):
    flow_token, state = _login_url(api_client)
    _mock_code_exchange(monkeypatch)
    _mock_verify(monkeypatch, {"oid": "oid-new", "email": "new@example.com", "name": "New", "tid": "test-tenant"})

    resp = api_client.post(
        "/api/auth/entra/token",
        json={"code": "abc", "state": state, "flow_token": flow_token},
    )
    assert resp.status_code == 403
    created = db.query(User).filter_by(email="new@example.com").one()
    assert created.is_active is False
    assert created.entra_object_id == "oid-new"


def test_token_exchange_code_rejected_401(api_client, db, entra_mode, monkeypatch):
    flow_token, state = _login_url(api_client)
    _mock_code_exchange(monkeypatch, ok=False)
    resp = api_client.post(
        "/api/auth/entra/token",
        json={"code": "abc", "state": state, "flow_token": flow_token},
    )
    assert resp.status_code == 401
