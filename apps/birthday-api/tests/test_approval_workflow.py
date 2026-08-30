"""Semi-automation future-state plan §K/§F tests: "verification is the
approval" — a manually-created order starts PENDING_VERIFICATION; marking
the address VERIFIED either auto-releases a standard order straight to
SENT_TO_SUPPLIER, or routes a flagged order to REQUIRES_REVIEW for a
one-click Confirm & release. Readiness gating and the
never-actioned-order delete rule are unchanged in spirit."""

from __future__ import annotations

from datetime import date, timedelta

from tests.conftest import headers_for


def _create_order(api_client, headers, employee_id="emp-appr-1"):
    payload = {
        "employee_id": employee_id,
        "employee_name": "Approval Test",
        "employee_email": "approval.test@example.com",
        "birthday_date": str(date.today() + timedelta(days=20)),
        "office_location": "Colombo",
    }
    return api_client.post("/api/birthday/orders", json=payload, headers=headers).json()


def test_manual_order_starts_pending_verification(api_client, db):
    headers = headers_for(60, role="BIRTHDAY_ADMIN")
    created = _create_order(api_client, headers)
    assert created["status"] == "PENDING_VERIFICATION"


def test_verify_without_supplier_routes_to_requires_attention(api_client, db):
    """Verifying an order that isn't otherwise ready (no supplier
    assigned) cannot auto-release — it must land in the exception queue,
    not silently stay PENDING_VERIFICATION or error out."""
    headers = headers_for(61, role="BIRTHDAY_ADMIN")
    created = _create_order(api_client, headers, "emp-appr-2")
    resp = api_client.post(
        f"/api/birthday/orders/{created['id']}/verify", json={}, headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["auto_released"] is False
    assert body["order"]["status"] == "REQUIRES_ATTENTION"


def test_standard_order_auto_releases_on_verification(api_client, db):
    """The core semi-automation behaviour (plan §F/§K): a fully-defaulted
    order auto-releases the instant its address is verified — no
    submit/approve/send click."""
    from app.models.supplier import Supplier

    supplier = Supplier(name="Approval Supplier", primary_contact_email="appr@supplier.example.com")
    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    headers = headers_for(62, role="BIRTHDAY_ADMIN")
    created = _create_order(api_client, headers, "emp-appr-3")
    order_id = created["id"]

    from app.models.birthday_order import BirthdayOrder

    order = db.get(BirthdayOrder, order_id)
    order.supplier_id = supplier.id
    order.delivery_date = date.today() + timedelta(days=15)  # normal lead time
    db.commit()

    readiness = api_client.get(f"/api/birthday/orders/{order_id}/readiness", headers=headers).json()
    assert readiness["ready"] is False  # address not yet verified

    verify_resp = api_client.post(
        f"/api/birthday/orders/{order_id}/verify", json={}, headers=headers,
    )
    assert verify_resp.status_code == 200
    body = verify_resp.json()
    assert body["auto_released"] is True
    assert body["order"]["status"] == "SENT_TO_SUPPLIER"
    assert body["order"]["released_by"] is None  # SYSTEM-released, not a human approval click


def test_corrected_address_flags_for_review_instead_of_auto_releasing(api_client, db):
    from app.models.supplier import Supplier

    supplier = Supplier(name="Review Supplier", primary_contact_email="review@supplier.example.com")
    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    headers = headers_for(63, role="BIRTHDAY_ADMIN")
    created = _create_order(api_client, headers, "emp-appr-4")
    order_id = created["id"]

    from app.models.birthday_order import BirthdayOrder

    order = db.get(BirthdayOrder, order_id)
    order.supplier_id = supplier.id
    order.delivery_date = date.today() + timedelta(days=15)
    db.commit()

    verify_resp = api_client.post(
        f"/api/birthday/orders/{order_id}/verify", json={"corrected": True}, headers=headers,
    )
    assert verify_resp.status_code == 200
    body = verify_resp.json()
    assert body["auto_released"] is False
    assert body["order"]["status"] == "REQUIRES_REVIEW"

    confirm = api_client.post(
        f"/api/birthday/orders/{order_id}/confirm-release", json={}, headers=headers,
    )
    assert confirm.status_code == 200
    confirmed_order = confirm.json()
    assert confirmed_order["status"] == "SENT_TO_SUPPLIER"
    assert confirmed_order["released_by"] == 63  # a human confirmed this one


def test_confirm_release_rejects_non_review_orders(api_client, db):
    headers = headers_for(64, role="BIRTHDAY_ADMIN")
    created = _create_order(api_client, headers, "emp-appr-5")
    resp = api_client.post(
        f"/api/birthday/orders/{created['id']}/confirm-release", json={}, headers=headers,
    )
    assert resp.status_code == 409


def test_send_to_supplier_blocked_before_verification(api_client, db):
    from app.models.supplier import Supplier

    supplier = Supplier(name="Not Ready Supplier", primary_contact_email="notready@supplier.example.com")
    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    headers = headers_for(65, role="BIRTHDAY_ADMIN")
    created = _create_order(api_client, headers, "emp-appr-6")
    order_id = created["id"]

    from app.models.birthday_order import BirthdayOrder

    order = db.get(BirthdayOrder, order_id)
    order.supplier_id = supplier.id
    db.commit()

    resp = api_client.post(f"/api/birthday/orders/{order_id}/send-to-supplier", headers=headers)
    assert resp.status_code == 409
    assert "address" in resp.json()["detail"].lower()


def test_verify_requires_permission(api_client, db):
    headers_admin = headers_for(66, role="BIRTHDAY_ADMIN")
    created = _create_order(api_client, headers_admin, "emp-appr-7")

    resp = api_client.post(
        f"/api/birthday/orders/{created['id']}/verify", json={},
        headers=headers_for(67, role="BIRTHDAY_USER"),
    )
    assert resp.status_code == 403


def test_delete_allowed_only_for_never_actioned_order(api_client, db):
    headers = headers_for(68, role="BIRTHDAY_ADMIN")
    created = _create_order(api_client, headers, "emp-appr-8")
    order_id = created["id"]

    resp = api_client.delete(f"/api/birthday/orders/{order_id}", headers=headers)
    assert resp.status_code == 204

    resp2 = api_client.get(f"/api/birthday/orders/{order_id}", headers=headers)
    assert resp2.status_code == 404


def test_delete_rejected_once_order_has_left_pending_verification(api_client, db):
    headers = headers_for(69, role="BIRTHDAY_ADMIN")
    created = _create_order(api_client, headers, "emp-appr-9")
    order_id = created["id"]

    held = api_client.post(f"/api/birthday/orders/{order_id}/hold", json={"hold_reason": "check"}, headers=headers)
    assert held.status_code == 200
    assert held.json()["status"] == "ON_HOLD"

    resp = api_client.delete(f"/api/birthday/orders/{order_id}", headers=headers)
    assert resp.status_code == 409

    # Order must still exist and be inspectable (non-destructive path).
    still_there = api_client.get(f"/api/birthday/orders/{order_id}", headers=headers)
    assert still_there.status_code == 200
