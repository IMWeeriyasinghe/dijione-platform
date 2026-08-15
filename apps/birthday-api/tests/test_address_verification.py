"""Address-verification workflow tests: default status, P&C-driven
change, audit trail, and its effect on supplier-send gating."""

from __future__ import annotations

from datetime import date, timedelta

from tests.conftest import headers_for


def _make_verifiable_order(db):
    from app.models.birthday_order import BirthdayOrder
    from app.models.supplier import Supplier

    supplier = Supplier(name="Verify Test Supplier", primary_contact_email="verify@supplier.example.com")
    db.add(supplier)
    db.flush()

    order = BirthdayOrder(
        order_reference="BDAY-EMPverify-2026-00001",
        employee_id="emp-verify",
        employee_name="Verify Test",
        employee_email="verify.test@example.com",
        birthday_date=date.today() + timedelta(days=10),
        birthday_year=(date.today() + timedelta(days=10)).year,
        office_location="Colombo",
        status="PLANNED",
        supplier_id=supplier.id,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def test_default_address_verification_status_is_not_checked(db):
    order = _make_verifiable_order(db)
    assert order.address_verification_status == "NOT_CHECKED"


def test_pnc_can_change_address_verification_status(db, platform_calls):
    from app.core.constants import AddressVerificationStatus
    from app.services.address_verification_service import set_address_verification_status

    order = _make_verifiable_order(db)
    updated = set_address_verification_status(
        db, order, AddressVerificationStatus.VERIFIED, actor_id=7, note="Confirmed via phone call with employee",
    )
    assert updated.address_verification_status == "VERIFIED"


def test_address_verification_change_is_audited_without_address_content(db, platform_calls):
    from app.core.constants import AddressVerificationStatus
    from app.services.address_verification_service import set_address_verification_status

    order = _make_verifiable_order(db)
    set_address_verification_status(
        db, order, AddressVerificationStatus.VERIFICATION_REQUESTED, actor_id=7, note=None,
    )

    events = [
        c for c in platform_calls["audit_events"]
        if c.get("action") == "birthday.order.address_verification_change"
    ]
    assert len(events) == 1
    event = events[0]
    assert event["actor_id"] == 7
    assert event["entity_id"] == order.id
    assert event["previous_state"] == {"address_verification_status": "NOT_CHECKED"}
    assert event["new_state"] == {"address_verification_status": "VERIFICATION_REQUESTED"}
    # No street-address content anywhere in the payload — this service has
    # no address field to leak by construction, but assert the shape stays
    # status-only as a regression guard.
    assert set(event["previous_state"].keys()) == {"address_verification_status"}
    assert set(event["new_state"].keys()) == {"address_verification_status"}


def test_address_verification_change_writes_order_event(db):
    from app.core.constants import AddressVerificationStatus
    from app.models.order_event import OrderEvent
    from app.services.address_verification_service import set_address_verification_status

    order = _make_verifiable_order(db)
    set_address_verification_status(db, order, AddressVerificationStatus.NEEDS_UPDATE, actor_id=7)

    events = db.query(OrderEvent).filter_by(order_id=order.id, event_type="ADDRESS_VERIFICATION_CHANGE").all()
    assert len(events) == 1
    assert events[0].from_status == "NOT_CHECKED"
    assert events[0].to_status == "NEEDS_UPDATE"


def test_send_to_supplier_blocked_until_verified_then_permitted(api_client, db):
    """End-to-end: NOT_CHECKED blocks send; setting VERIFIED via the P&C
    endpoint then permits it."""
    from app.models.birthday_order import BirthdayOrder
    from app.models.supplier import Supplier

    supplier = Supplier(name="E2E Supplier", primary_contact_email="e2e@supplier.example.com")
    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    headers = headers_for(50, role="BIRTHDAY_ADMIN")
    payload = {
        "employee_id": "emp-e2e",
        "employee_name": "E2E Test",
        "employee_email": "e2e.test@example.com",
        "birthday_date": str(date.today() + timedelta(days=15)),
        "office_location": "Colombo",
    }
    created = api_client.post("/api/birthday/orders", json=payload, headers=headers).json()
    order_id = created["id"]

    order = db.get(BirthdayOrder, order_id)
    order.supplier_id = supplier.id
    order.status = "APPROVED"  # bypass the approval gate directly so this test isolates the address gate
    db.commit()

    blocked = api_client.post(f"/api/birthday/orders/{order_id}/send-to-supplier", headers=headers)
    assert blocked.status_code == 409

    verify_resp = api_client.patch(
        f"/api/birthday/orders/{order_id}/address-verification",
        json={"status": "VERIFIED", "note": "Confirmed with employee directly"},
        headers=headers,
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["address_verification_status"] == "VERIFIED"

    allowed = api_client.post(f"/api/birthday/orders/{order_id}/send-to-supplier", headers=headers)
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "SENT_TO_SUPPLIER"


def test_update_delivery_address_sets_manual_correction_source(db, platform_calls):
    from app.services.address_verification_service import update_delivery_address

    order = _make_verifiable_order(db)
    assert order.delivery_address_source is None

    updated = update_delivery_address(
        db, order,
        {"delivery_city": "Kandy", "delivery_country": "Sri Lanka"},
        actor_id=7,
    )
    assert updated.delivery_city == "Kandy"
    assert updated.delivery_country == "Sri Lanka"
    assert updated.delivery_address_source == "MANUAL_CORRECTION"


def test_update_delivery_address_audit_logs_field_names_not_values(db, platform_calls):
    from app.services.address_verification_service import update_delivery_address

    order = _make_verifiable_order(db)
    update_delivery_address(
        db, order,
        {"delivery_address_line1": "42 Some Private Street", "delivery_city": "Galle"},
        actor_id=7,
    )

    events = [c for c in platform_calls["audit_events"] if c.get("action") == "birthday.order.address_corrected"]
    assert len(events) == 1
    event = events[0]
    assert event["entity_id"] == order.id
    assert set(event["metadata"]["fields_changed"]) == {"delivery_address_line1", "delivery_city"}
    # No address content anywhere in the audit payload.
    assert "42 Some Private Street" not in str(event)
    assert "Galle" not in str(event)


def test_update_delivery_address_endpoint(api_client, db):
    headers = headers_for(52, role="BIRTHDAY_ADMIN")
    payload = {
        "employee_id": "emp-addr-edit",
        "employee_name": "Addr Edit Test",
        "employee_email": "addr.edit@example.com",
        "birthday_date": str(date.today() + timedelta(days=15)),
        "office_location": "Colombo",
    }
    created = api_client.post("/api/birthday/orders", json=payload, headers=headers).json()
    order_id = created["id"]

    resp = api_client.patch(
        f"/api/birthday/orders/{order_id}/delivery-address",
        json={"delivery_city": "Matara", "delivery_state_province": "Southern"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["delivery_city"] == "Matara"
    assert body["delivery_state_province"] == "Southern"
    assert body["delivery_address_source"] == "MANUAL_CORRECTION"


def test_address_verification_endpoint_rejects_invalid_status(api_client, db):
    from app.models.birthday_order import BirthdayOrder  # noqa: F401

    headers = headers_for(51, role="BIRTHDAY_ADMIN")
    payload = {
        "employee_id": "emp-invalid",
        "employee_name": "Invalid Status Test",
        "employee_email": "invalid@example.com",
        "birthday_date": str(date.today() + timedelta(days=15)),
        "office_location": "Colombo",
    }
    created = api_client.post("/api/birthday/orders", json=payload, headers=headers).json()
    order_id = created["id"]

    resp = api_client.patch(
        f"/api/birthday/orders/{order_id}/address-verification",
        json={"status": "NOT_A_REAL_STATUS"},
        headers=headers,
    )
    assert resp.status_code == 422
