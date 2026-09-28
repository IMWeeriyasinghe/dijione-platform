"""Birthday Supplier Portal — Microsoft Entra ID B2B guest sign-in.

Entra's JWKS + the authorization-code exchange are mocked (no network).
Entra proves identity; an ACTIVE ``SupplierUser`` grants DijiBirthday
access. Everything fails closed.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

ENTRA_ENV = {
    "SUPPLIER_AUTH_MODE": "entra",
    "SUPPLIER_ENTRA_TENANT_ID": "test-tenant",
    "SUPPLIER_ENTRA_CLIENT_ID": "supplier-client",
    "SUPPLIER_ENTRA_CLIENT_SECRET": "supplier-secret",
    "SUPPLIER_ENTRA_REDIRECT_URI": "http://localhost:3000/api/auth/callback",
}


@pytest.fixture()
def entra_mode(monkeypatch):
    from app.core.config import get_settings
    from app.core.supplier_entra import get_supplier_entra_verifier

    for k, v in ENTRA_ENV.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    get_supplier_entra_verifier.cache_clear()
    yield
    get_settings.cache_clear()
    get_supplier_entra_verifier.cache_clear()


def _mock_code_exchange(monkeypatch, *, id_token="fake.id.token", ok=True):
    class _Resp:
        status_code = 200 if ok else 400

        def json(self):
            return {"id_token": id_token} if ok else {"error": "invalid_grant"}

    monkeypatch.setattr("app.api.routes.supplier_auth_entra.httpx.post", lambda *a, **k: _Resp())


def _mock_verify(monkeypatch, claims):
    monkeypatch.setattr(
        "app.core.supplier_entra.SupplierEntraVerifier.verify_id_token",
        lambda self, id_token, nonce=None: claims,
    )


def _mock_verify_raises(monkeypatch, exc):
    def _raise(self, id_token, nonce=None):
        raise exc

    monkeypatch.setattr(
        "app.core.supplier_entra.SupplierEntraVerifier.verify_id_token", _raise
    )


def _login_flow(api_client):
    resp = api_client.get("/api/birthday/supplier/auth/login-url")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    state = parse_qs(urlparse(body["authorize_url"]).query)["state"][0]
    return body["flow_token"], state


def _seed_supplier_user(db, *, email="guest@supplier.example.com", status="ACTIVE", oid=None):
    from app.models.supplier import Supplier
    from app.models.supplier_user import SupplierUser

    supplier = Supplier(name=f"S-{email}", primary_contact_email=email)
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    su = SupplierUser(
        supplier_id=supplier.id, email=email, full_name="Guest", status=status, entra_object_id=oid
    )
    db.add(su)
    db.commit()
    db.refresh(su)
    return supplier, su


# --- mode / config -------------------------------------------------------

def test_config_reports_dev_by_default(api_client):
    assert api_client.get("/api/birthday/supplier/auth/config").json() == {
        "supplier_auth_mode": "dev"
    }


def test_config_reports_entra(api_client, entra_mode):
    assert api_client.get("/api/birthday/supplier/auth/config").json() == {
        "supplier_auth_mode": "entra"
    }


def test_login_url_501_when_not_entra(api_client):
    assert api_client.get("/api/birthday/supplier/auth/login-url").status_code == 501


def test_login_url_501_when_entra_unconfigured(api_client, monkeypatch):
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("SUPPLIER_AUTH_MODE", "entra")  # but no SUPPLIER_ENTRA_*
    get_settings.cache_clear()
    try:
        assert api_client.get("/api/birthday/supplier/auth/login-url").status_code == 501
    finally:
        get_settings.cache_clear()


def test_login_url_ok_and_pkce_when_configured(api_client, entra_mode):
    body = api_client.get("/api/birthday/supplier/auth/login-url").json()
    q = parse_qs(urlparse(body["authorize_url"]).query)
    assert q["client_id"] == ["supplier-client"]
    assert q["code_challenge_method"] == ["S256"]
    assert q["scope"] == ["openid profile email"]
    assert body["flow_token"]


# --- return_to (order deep-link) round trip ----------------------------

def _login_flow_with_return_to(api_client, return_to):
    resp = api_client.get(
        "/api/birthday/supplier/auth/login-url", params={"return_to": return_to}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    state = parse_qs(urlparse(body["authorize_url"]).query)["state"][0]
    return body["flow_token"], state


def test_valid_return_to_survives_the_full_login_round_trip(api_client, db, entra_mode, monkeypatch):
    _seed_supplier_user(db, email="deeplink@supplier.example.com")
    flow, state = _login_flow_with_return_to(api_client, "/orders/42")
    _mock_code_exchange(monkeypatch)
    _mock_verify(monkeypatch, {"oid": "oid-dl", "email": "deeplink@supplier.example.com", "tid": "test-tenant"})

    resp = api_client.post(
        "/api/birthday/supplier/auth/token",
        json={"code": "abc", "state": state, "flow_token": flow},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["return_to"] == "/orders/42"


def test_no_return_to_yields_none(api_client, db, entra_mode, monkeypatch):
    _seed_supplier_user(db, email="noreturn@supplier.example.com")
    flow, state = _login_flow(api_client)
    _mock_code_exchange(monkeypatch)
    _mock_verify(monkeypatch, {"oid": "oid-nr", "email": "noreturn@supplier.example.com", "tid": "test-tenant"})

    resp = api_client.post(
        "/api/birthday/supplier/auth/token",
        json={"code": "abc", "state": state, "flow_token": flow},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["return_to"] is None


@pytest.mark.parametrize(
    "malicious_return_to",
    [
        "https://evil.example.com/phish",
        "//evil.example.com/phish",
        "/orders/1;javascript:alert(1)",
        "orders/1",  # not rooted — must start with "/"
        "/orders/1\nSet-Cookie: x=1",
    ],
)
def test_unsafe_return_to_is_dropped_not_forwarded(
    api_client, db, entra_mode, monkeypatch, malicious_return_to
):
    """An open-redirect / header-injection attempt must never reach the
    signed flow token or the token-exchange response — it is silently
    dropped (falls back to no return_to), never rejected with an error
    that would leak that the value was inspected."""
    _seed_supplier_user(db, email="attacker-input@supplier.example.com")
    flow, state = _login_flow_with_return_to(api_client, malicious_return_to)
    _mock_code_exchange(monkeypatch)
    _mock_verify(
        monkeypatch,
        {"oid": "oid-atk", "email": "attacker-input@supplier.example.com", "tid": "test-tenant"},
    )

    resp = api_client.post(
        "/api/birthday/supplier/auth/token",
        json={"code": "abc", "state": state, "flow_token": flow},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["return_to"] is None
    assert "evil.example.com" not in resp.text
    assert "javascript:" not in resp.text


# --- token exchange: success + linking --------------------------------

def test_active_guest_with_supplier_user_gets_working_portal_token(api_client, db, entra_mode, monkeypatch):
    _supplier, su = _seed_supplier_user(db, email="known@supplier.example.com")
    flow, state = _login_flow(api_client)
    _mock_code_exchange(monkeypatch)
    _mock_verify(monkeypatch, {"oid": "oid-1", "email": "known@supplier.example.com", "tid": "test-tenant"})

    resp = api_client.post(
        "/api/birthday/supplier/auth/token",
        json={"code": "abc", "state": state, "flow_token": flow},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    assert "secret" not in resp.text.lower()

    # first login stamped the durable oid onto the row
    db.refresh(su)
    assert su.entra_object_id == "oid-1"

    portal = api_client.get(
        "/api/birthday/portal/orders", headers={"Authorization": f"Bearer {token}"}
    )
    assert portal.status_code == 200
    assert portal.json()["total"] == 0


def test_second_login_matches_by_oid_even_if_email_changed(api_client, db, entra_mode, monkeypatch):
    _supplier, su = _seed_supplier_user(db, email="orig@supplier.example.com", oid="oid-2")
    flow, state = _login_flow(api_client)
    _mock_code_exchange(monkeypatch)
    # email absent / different, but oid matches the linked row
    _mock_verify(monkeypatch, {"oid": "oid-2", "tid": "test-tenant"})

    resp = api_client.post(
        "/api/birthday/supplier/auth/token",
        json={"code": "abc", "state": state, "flow_token": flow},
    )
    assert resp.status_code == 200, resp.text


# --- token exchange: fail-closed --------------------------------------

def test_valid_identity_without_supplier_user_denied(api_client, db, entra_mode, monkeypatch):
    flow, state = _login_flow(api_client)
    _mock_code_exchange(monkeypatch)
    _mock_verify(monkeypatch, {"oid": "oid-x", "email": "nobody@random.example.com", "tid": "test-tenant"})

    resp = api_client.post(
        "/api/birthday/supplier/auth/token",
        json={"code": "abc", "state": state, "flow_token": flow},
    )
    assert resp.status_code == 403
    assert "not authorised" in resp.json()["detail"].lower()


def test_inactive_supplier_user_denied(api_client, db, entra_mode, monkeypatch):
    _seed_supplier_user(db, email="inactive@supplier.example.com", status="INACTIVE")
    flow, state = _login_flow(api_client)
    _mock_code_exchange(monkeypatch)
    _mock_verify(monkeypatch, {"oid": "oid-i", "email": "inactive@supplier.example.com", "tid": "test-tenant"})

    resp = api_client.post(
        "/api/birthday/supplier/auth/token",
        json={"code": "abc", "state": state, "flow_token": flow},
    )
    assert resp.status_code == 403


def test_missing_email_and_oid_fails_closed(api_client, db, entra_mode, monkeypatch):
    _seed_supplier_user(db, email="present@supplier.example.com")
    flow, state = _login_flow(api_client)
    _mock_code_exchange(monkeypatch)
    _mock_verify(monkeypatch, {"tid": "test-tenant"})  # no oid, no email

    resp = api_client.post(
        "/api/birthday/supplier/auth/token",
        json={"code": "abc", "state": state, "flow_token": flow},
    )
    assert resp.status_code == 403


def test_ext_upn_not_treated_as_email(api_client, db, entra_mode, monkeypatch):
    """A B2B guest's rewritten #EXT# UPN must not match a SupplierUser."""
    _seed_supplier_user(db, email="real@supplier.example.com")
    flow, state = _login_flow(api_client)
    _mock_code_exchange(monkeypatch)
    _mock_verify(
        monkeypatch,
        {
            "oid": "oid-ext",
            "preferred_username": "real_supplier.example.com#EXT#@dijitalteam.onmicrosoft.com",
            "tid": "test-tenant",
        },
    )
    resp = api_client.post(
        "/api/birthday/supplier/auth/token",
        json={"code": "abc", "state": state, "flow_token": flow},
    )
    assert resp.status_code == 403


@pytest.mark.parametrize(
    "exc_msg",
    [
        "token tenant (tid) does not match SUPPLIER_ENTRA_TENANT_ID",
        "Invalid audience",
        "Signature verification failed",
        "Signature has expired",
        "nonce mismatch",
    ],
)
def test_bad_id_token_401(api_client, db, entra_mode, monkeypatch, exc_msg):
    from app.core.supplier_entra import InvalidSupplierTokenError

    flow, state = _login_flow(api_client)
    _mock_code_exchange(monkeypatch)
    _mock_verify_raises(monkeypatch, InvalidSupplierTokenError(exc_msg))

    resp = api_client.post(
        "/api/birthday/supplier/auth/token",
        json={"code": "abc", "state": state, "flow_token": flow},
    )
    assert resp.status_code == 401


def test_entra_rejects_code_401(api_client, db, entra_mode, monkeypatch):
    flow, state = _login_flow(api_client)
    _mock_code_exchange(monkeypatch, ok=False)
    resp = api_client.post(
        "/api/birthday/supplier/auth/token",
        json={"code": "abc", "state": state, "flow_token": flow},
    )
    assert resp.status_code == 401


def test_state_mismatch_400(api_client, db, entra_mode, monkeypatch):
    flow, _state = _login_flow(api_client)
    _mock_code_exchange(monkeypatch)
    resp = api_client.post(
        "/api/birthday/supplier/auth/token",
        json={"code": "abc", "state": "WRONG", "flow_token": flow},
    )
    assert resp.status_code == 400


# --- tenant isolation on the minted token ------------------------------

def test_supplier_a_token_cannot_read_supplier_b_orders(api_client, db, entra_mode, monkeypatch):
    from datetime import date, timedelta

    from app.models.birthday_order import BirthdayOrder

    _sa, sua = _seed_supplier_user(db, email="a@supplier.example.com")
    sb, _sub = _seed_supplier_user(db, email="b@supplier.example.com")

    # an order that belongs to supplier B
    bday = date.today() + timedelta(days=10)
    order_b = BirthdayOrder(
        order_reference="BDAY-EMPemp-b-1-2026-00001",
        employee_id="emp-b-1",
        employee_name="B Person",
        employee_email="b.person@example.com",
        birthday_date=bday,
        birthday_year=bday.year,
        office_location="Colombo",
        quantity=1,
        status="SENT_TO_SUPPLIER",
        supplier_id=sb.id,
        address_verification_status="VERIFIED",
    )
    db.add(order_b)
    db.commit()
    db.refresh(order_b)

    flow, state = _login_flow(api_client)
    _mock_code_exchange(monkeypatch)
    _mock_verify(monkeypatch, {"oid": "oid-a", "email": "a@supplier.example.com", "tid": "test-tenant"})
    token_a = api_client.post(
        "/api/birthday/supplier/auth/token",
        json={"code": "abc", "state": state, "flow_token": flow},
    ).json()["access_token"]

    # supplier A cannot see the count and cannot fetch B's order by id
    lst = api_client.get(
        "/api/birthday/portal/orders", headers={"Authorization": f"Bearer {token_a}"}
    )
    assert lst.status_code == 200 and lst.json()["total"] == 0
    one = api_client.get(
        f"/api/birthday/portal/orders/{order_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert one.status_code == 404
