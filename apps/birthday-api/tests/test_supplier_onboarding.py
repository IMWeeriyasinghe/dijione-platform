"""Phase 1 §1.6 — SupplierUser onboarding-state visibility + setup readiness."""

from __future__ import annotations

from tests.conftest import headers_for


def _admin():
    return headers_for(960, role="BIRTHDAY_ADMIN")


def _supplier(api_client, admin, **extra):
    body = {"name": "Onboard Bakery", "primary_contact_email": "ob@bakery.example.com"}
    body.update(extra)
    return api_client.post("/api/birthday/suppliers", json=body, headers=admin).json()


def test_onboarding_state_progresses(api_client, db):
    admin = _admin()
    sup = _supplier(api_client, admin)
    # send_invitation=False here: this test is specifically about the
    # onboarding_state state machine (including the legacy manual
    # mark_invited path below), not the new auto-invite-on-create default —
    # that has its own tests in test_supplier_invitation.py.
    user = api_client.post(
        f"/api/birthday/suppliers/{sup['id']}/users",
        json={"email": "baker@ob.example.com", "full_name": "Baker", "send_invitation": False},
        headers=admin,
    ).json()
    assert user["onboarding_state"] == "NOT_INVITED"

    invited = api_client.patch(
        f"/api/birthday/suppliers/{sup['id']}/users/{user['id']}",
        json={"mark_invited": True}, headers=admin,
    ).json()
    assert invited["onboarding_state"] == "INVITED" and invited["invited_at"] is not None

    linked = api_client.patch(
        f"/api/birthday/suppliers/{sup['id']}/users/{user['id']}",
        json={"entra_object_id": "oid-onboard-1"}, headers=admin,
    ).json()
    assert linked["onboarding_state"] == "LINKED" and linked["linked_at"] is not None

    # a dev-persona login stamps last_login_at -> ACTIVE
    from app.models.supplier_user import SupplierUser
    from app.services.supplier_auth import mint_supplier_session_token, record_supplier_login

    su = db.get(SupplierUser, user["id"])
    mint_supplier_session_token(su)
    record_supplier_login(db, su)
    got = api_client.get(
        f"/api/birthday/suppliers/{sup['id']}/users", headers=admin,
    ).json()[0]
    assert got["onboarding_state"] == "ACTIVE" and got["last_login_at"] is not None

    # deactivate -> INACTIVE wins
    off = api_client.patch(
        f"/api/birthday/suppliers/{sup['id']}/users/{user['id']}",
        json={"status": "INACTIVE"}, headers=admin,
    ).json()
    assert off["onboarding_state"] == "INACTIVE"


def test_dev_supplier_login_stamps_last_login(api_client, db):
    from app.models.supplier import Supplier
    from app.models.supplier_user import SupplierUser

    supplier = Supplier(name="Dev Login Co", primary_contact_email="d@d.example.com")
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    su = SupplierUser(supplier_id=supplier.id, email="dev@login.example.com", status="ACTIVE")
    db.add(su)
    db.commit()
    db.refresh(su)

    r = api_client.post(
        "/api/birthday/internal/dev/supplier-login", json={"supplier_user_id": su.id},
    )
    assert r.status_code == 200
    db.refresh(su)
    assert su.last_login_at is not None


def test_setup_readiness_panel(api_client, db):
    admin = _admin()
    sup = _supplier(api_client, admin)
    r = api_client.get(f"/api/birthday/suppliers/{sup['id']}/readiness", headers=admin).json()
    assert r["ready"] is False
    assert "no service location" in r["missing"]
    assert "no active Entra-linked supplier user" in r["missing"]

    api_client.post(
        f"/api/birthday/suppliers/{sup['id']}/locations",
        json={"office_location": "Colombo"}, headers=admin,
    )
    u = api_client.post(
        f"/api/birthday/suppliers/{sup['id']}/users",
        json={"email": "u@ob.example.com"}, headers=admin,
    ).json()
    api_client.patch(
        f"/api/birthday/suppliers/{sup['id']}/users/{u['id']}",
        json={"entra_object_id": "oid-ready-1"}, headers=admin,
    )
    r2 = api_client.get(f"/api/birthday/suppliers/{sup['id']}/readiness", headers=admin).json()
    assert r2["ready"] is True and r2["missing"] == []
