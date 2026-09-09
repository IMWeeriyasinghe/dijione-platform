"""Phase 1.5 §C — read-only supplier impersonation.

An internal ``BIRTHDAY_ADMIN`` mints a 30-minute supplier session token
that carries only ``birthday.portal.access``. Every mutating portal route
(gated on ``birthday.portal.respond``) 403s for that token, while reads
succeed and ``/portal/me`` reports ``read_only: true``.
"""

from __future__ import annotations

from datetime import date, timedelta

from tests.conftest import headers_for


def _supplier_with_user(db, *, user_status="ACTIVE"):
    from app.models.supplier import Supplier
    from app.models.supplier_user import SupplierUser

    supplier = Supplier(name="Impersonation Bakery", primary_contact_email="imp@bakery.example.com")
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    user = SupplierUser(
        supplier_id=supplier.id,
        email="imp-user@bakery.example.com",
        full_name="Imp User",
        status=user_status,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return supplier, user


def _sent_order(db, supplier, employee_id="imp-emp-1"):
    from app.models.birthday_order import BirthdayOrder

    order = BirthdayOrder(
        order_reference=f"BDAY-EMP{employee_id}-2026-00001",
        employee_id=employee_id,
        employee_name="Imp Recipient",
        employee_email="imp.recipient@example.com",
        birthday_date=date.today() + timedelta(days=10),
        birthday_year=(date.today() + timedelta(days=10)).year,
        office_location="Colombo",
        quantity=1,
        status="SENT_TO_SUPPLIER",
        supplier_id=supplier.id,
        address_verification_status="VERIFIED",
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def _impersonate(api_client, supplier, user):
    resp = api_client.post(
        f"/api/birthday/suppliers/{supplier.id}/users/{user.id}/impersonate",
        headers=headers_for(500, role="BIRTHDAY_ADMIN"),
    )
    return resp


def test_impersonation_requires_suppliers_manage(api_client, db):
    supplier, user = _supplier_with_user(db)
    resp = api_client.post(
        f"/api/birthday/suppliers/{supplier.id}/users/{user.id}/impersonate",
        headers=headers_for(1, role="BIRTHDAY_USER"),
    )
    assert resp.status_code == 403


def test_impersonation_404_for_unknown_user(api_client, db):
    supplier, _user = _supplier_with_user(db)
    resp = api_client.post(
        f"/api/birthday/suppliers/{supplier.id}/users/999999/impersonate",
        headers=headers_for(500, role="BIRTHDAY_ADMIN"),
    )
    assert resp.status_code == 404


def test_impersonation_409_for_inactive_user(api_client, db):
    supplier, user = _supplier_with_user(db, user_status="INACTIVE")
    resp = _impersonate(api_client, supplier, user)
    assert resp.status_code == 409


def test_impersonation_token_is_read_only_end_to_end(api_client, db, platform_calls):
    supplier, user = _supplier_with_user(db)
    order = _sent_order(db, supplier)

    resp = _impersonate(api_client, supplier, user)
    assert resp.status_code == 200
    body = resp.json()
    assert body["expires_in"] == 1800
    token = body["access_token"]
    ro = {"Authorization": f"Bearer {token}"}

    # /portal/me reports the read-only preview.
    me = api_client.get("/api/birthday/portal/me", headers=ro)
    assert me.status_code == 200
    assert me.json() == {
        "supplier_name": "Impersonation Bakery",
        "user_name": "Imp User",
        "read_only": True,
    }

    # Reads work.
    assert api_client.get("/api/birthday/portal/orders", headers=ro).status_code == 200
    assert api_client.get("/api/birthday/portal/dashboard", headers=ro).status_code == 200
    assert api_client.get(f"/api/birthday/portal/orders/{order.id}", headers=ro).status_code == 200

    # Every mutating route 403s — no per-route change, the missing
    # birthday.portal.respond permission does it.
    assert api_client.post(
        f"/api/birthday/portal/orders/{order.id}/accept", headers=ro
    ).status_code == 403
    assert api_client.patch(
        f"/api/birthday/portal/orders/{order.id}/status",
        json={"status": "PREPARING"}, headers=ro,
    ).status_code == 403
    assert api_client.post(
        f"/api/birthday/portal/orders/{order.id}/issues",
        json={"type": "OTHER", "detail": "x"}, headers=ro,
    ).status_code == 403
    assert api_client.post(
        f"/api/birthday/portal/orders/{order.id}/messages",
        json={"body": "hello"}, headers=ro,
    ).status_code == 403

    # The impersonation was audited.
    actions = [c.get("action") for c in platform_calls["audit_events"]]
    assert "birthday.supplier.impersonate" in actions


def test_real_supplier_token_still_can_act(api_client, db):
    """Guard against the read-only change leaking into the normal mint —
    a genuine supplier session keeps birthday.portal.respond."""
    from tests.conftest import supplier_headers_for

    supplier, _user = _supplier_with_user(db)
    order = _sent_order(db, supplier, employee_id="imp-emp-2")
    resp = api_client.post(
        f"/api/birthday/portal/orders/{order.id}/accept",
        headers=supplier_headers_for(db, supplier),
    )
    assert resp.status_code == 200
