"""Phase-Next §2/§3 approval workflow tests: DRAFT -> READY_FOR_APPROVAL ->
APPROVED/REJECTED, readiness gating, and the draft-only delete rule."""

from __future__ import annotations

from datetime import date, timedelta

from tests.conftest import headers_for


def _create_draft_order(api_client, headers, employee_id="emp-appr-1"):
    payload = {
        "employee_id": employee_id,
        "employee_name": "Approval Test",
        "employee_email": "approval.test@example.com",
        "birthday_date": str(date.today() + timedelta(days=20)),
        "office_location": "Colombo",
    }
    return api_client.post("/api/birthday/orders", json=payload, headers=headers).json()


def test_manual_order_starts_draft(api_client, db):
    headers = headers_for(60, role="BIRTHDAY_ADMIN")
    created = _create_draft_order(api_client, headers)
    assert created["status"] == "DRAFT"


def test_submit_for_approval_fails_when_not_ready(api_client, db):
    headers = headers_for(61, role="BIRTHDAY_ADMIN")
    created = _create_draft_order(api_client, headers, "emp-appr-2")
    resp = api_client.post(f"/api/birthday/orders/{created['id']}/submit-for-approval", headers=headers)
    assert resp.status_code == 409
    body = resp.json()["detail"]
    assert "supplier_not_assigned" in body["missing"]
    assert "address_not_verified" in body["missing"]


def test_full_approval_lifecycle(api_client, db):
    from app.models.supplier import Supplier

    supplier = Supplier(name="Approval Supplier", primary_contact_email="appr@supplier.example.com")
    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    headers = headers_for(62, role="BIRTHDAY_ADMIN")
    created = _create_draft_order(api_client, headers, "emp-appr-3")
    order_id = created["id"]

    from app.models.birthday_order import BirthdayOrder

    order = db.get(BirthdayOrder, order_id)
    order.supplier_id = supplier.id
    db.commit()

    verify_resp = api_client.patch(
        f"/api/birthday/orders/{order_id}/address-verification",
        json={"status": "VERIFIED"},
        headers=headers,
    )
    assert verify_resp.status_code == 200

    readiness = api_client.get(f"/api/birthday/orders/{order_id}/readiness", headers=headers).json()
    assert readiness["ready"] is True

    submitted = api_client.post(f"/api/birthday/orders/{order_id}/submit-for-approval", headers=headers)
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "READY_FOR_APPROVAL"

    approved = api_client.post(f"/api/birthday/orders/{order_id}/approve", headers=headers)
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"

    sent = api_client.post(f"/api/birthday/orders/{order_id}/send-to-supplier", headers=headers)
    assert sent.status_code == 200
    assert sent.json()["status"] == "SENT_TO_SUPPLIER"


def test_reject_requires_reason_and_is_terminal_ish(api_client, db):
    from app.models.supplier import Supplier

    supplier = Supplier(name="Reject Supplier", primary_contact_email="reject@supplier.example.com")
    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    headers = headers_for(63, role="BIRTHDAY_ADMIN")
    created = _create_draft_order(api_client, headers, "emp-appr-4")
    order_id = created["id"]

    from app.models.birthday_order import BirthdayOrder

    order = db.get(BirthdayOrder, order_id)
    order.supplier_id = supplier.id
    db.commit()
    api_client.patch(
        f"/api/birthday/orders/{order_id}/address-verification", json={"status": "VERIFIED"}, headers=headers,
    )
    api_client.post(f"/api/birthday/orders/{order_id}/submit-for-approval", headers=headers)

    rejected = api_client.post(
        f"/api/birthday/orders/{order_id}/reject", json={"reason": "wrong cake spec"}, headers=headers,
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"

    # Cannot be sent while REJECTED — not an allowed transition target.
    send_blocked = api_client.post(f"/api/birthday/orders/{order_id}/send-to-supplier", headers=headers)
    assert send_blocked.status_code == 409


def test_send_to_supplier_blocked_while_still_draft(api_client, db):
    from app.models.supplier import Supplier

    supplier = Supplier(name="Draft Block Supplier", primary_contact_email="draftblock@supplier.example.com")
    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    headers = headers_for(64, role="BIRTHDAY_ADMIN")
    created = _create_draft_order(api_client, headers, "emp-appr-5")
    order_id = created["id"]

    from app.models.birthday_order import BirthdayOrder

    order = db.get(BirthdayOrder, order_id)
    order.supplier_id = supplier.id
    order.address_verification_status = "VERIFIED"
    db.commit()

    resp = api_client.post(f"/api/birthday/orders/{order_id}/send-to-supplier", headers=headers)
    assert resp.status_code == 409
    assert "approved" in resp.json()["detail"].lower()


def test_approve_requires_permission(api_client, db):
    headers_admin = headers_for(65, role="BIRTHDAY_ADMIN")
    created = _create_draft_order(api_client, headers_admin, "emp-appr-6")

    resp = api_client.post(
        f"/api/birthday/orders/{created['id']}/approve", headers=headers_for(66, role="BIRTHDAY_USER"),
    )
    assert resp.status_code == 403


def test_delete_allowed_only_for_never_actioned_draft(api_client, db):
    headers = headers_for(67, role="BIRTHDAY_ADMIN")
    created = _create_draft_order(api_client, headers, "emp-appr-7")
    order_id = created["id"]

    resp = api_client.delete(f"/api/birthday/orders/{order_id}", headers=headers)
    assert resp.status_code == 204

    resp2 = api_client.get(f"/api/birthday/orders/{order_id}", headers=headers)
    assert resp2.status_code == 404


def test_delete_rejected_once_order_has_left_draft(api_client, db):
    headers = headers_for(68, role="BIRTHDAY_ADMIN")
    created = _create_draft_order(api_client, headers, "emp-appr-8")
    order_id = created["id"]

    held = api_client.post(f"/api/birthday/orders/{order_id}/hold", json={"hold_reason": "check"}, headers=headers)
    assert held.status_code == 200
    assert held.json()["status"] == "ON_HOLD"

    resp = api_client.delete(f"/api/birthday/orders/{order_id}", headers=headers)
    assert resp.status_code == 409

    # Order must still exist and be inspectable (non-destructive path).
    still_there = api_client.get(f"/api/birthday/orders/{order_id}", headers=headers)
    assert still_there.status_code == 200
