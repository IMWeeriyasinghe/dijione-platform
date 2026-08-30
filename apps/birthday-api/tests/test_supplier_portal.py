"""Phase-Next §5 supplier-portal tests. Cross-supplier isolation is the
single most important test here (CLAUDE.md §14's mandatory
isolation-testing pattern, applied to suppliers): supplier A's token must
never be able to read/act on supplier B's orders, by list, detail, or a
manipulated order id."""

from __future__ import annotations

from datetime import date, timedelta

from tests.conftest import headers_for, supplier_headers_for


def _make_sendable_order(db, *, supplier, employee_id):
    from app.models.birthday_order import BirthdayOrder

    order = BirthdayOrder(
        order_reference=f"BDAY-EMP{employee_id}-2026-00001",
        employee_id=employee_id,
        employee_name="Portal Test Employee",
        employee_email="portal.test@example.com",
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


def _make_suppliers(db):
    from app.models.supplier import Supplier

    supplier_a = Supplier(name="Supplier A", primary_contact_email="a@supplier.example.com")
    supplier_b = Supplier(name="Supplier B", primary_contact_email="b@supplier.example.com")
    db.add_all([supplier_a, supplier_b])
    db.commit()
    db.refresh(supplier_a)
    db.refresh(supplier_b)
    return supplier_a, supplier_b


def test_supplier_sees_only_own_orders_in_list(api_client, db):
    supplier_a, supplier_b = _make_suppliers(db)
    _make_sendable_order(db, supplier=supplier_a, employee_id="emp-portal-1")
    _make_sendable_order(db, supplier=supplier_b, employee_id="emp-portal-2")

    resp = api_client.get(
        "/api/birthday/portal/orders", headers=supplier_headers_for(db, supplier_a),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["employee_name"] == "Portal Test Employee"


def test_supplier_cannot_read_other_suppliers_order_by_id(api_client, db):
    supplier_a, supplier_b = _make_suppliers(db)
    order_b = _make_sendable_order(db, supplier=supplier_b, employee_id="emp-portal-3")

    resp = api_client.get(
        f"/api/birthday/portal/orders/{order_b.id}",
        headers=supplier_headers_for(db, supplier_a),
    )
    assert resp.status_code == 404


def test_supplier_cannot_act_on_other_suppliers_order(api_client, db):
    supplier_a, supplier_b = _make_suppliers(db)
    order_b = _make_sendable_order(db, supplier=supplier_b, employee_id="emp-portal-4")

    resp = api_client.post(
        f"/api/birthday/portal/orders/{order_b.id}/accept",
        headers=supplier_headers_for(db, supplier_a),
    )
    assert resp.status_code == 404


def test_supplier_cannot_choose_supplier_id_via_request(api_client, db):
    """Even if a malicious client tried to smuggle a supplier_id into the
    request, the server must ignore it entirely — SupplierScope is
    resolved only from the token claim."""
    supplier_a, supplier_b = _make_suppliers(db)
    _make_sendable_order(db, supplier=supplier_b, employee_id="emp-portal-5")

    # supplier_id is not even an accepted query param on this route — the
    # isolation boundary is structural, not a filter that could be bypassed.
    resp = api_client.get(
        f"/api/birthday/portal/orders?supplier_id={supplier_b.id}",
        headers=supplier_headers_for(db, supplier_a),
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_supplier_order_view_excludes_hr_fields(api_client, db):
    supplier_a, _ = _make_suppliers(db)
    _make_sendable_order(db, supplier=supplier_a, employee_id="emp-portal-6")

    resp = api_client.get(
        "/api/birthday/portal/orders", headers=supplier_headers_for(db, supplier_a),
    )
    item = resp.json()["items"][0]
    forbidden_fields = {
        "hire_date", "termination_date", "employment_status", "eligibility_reason",
        "employee_id", "employee_number",
    }
    assert forbidden_fields.isdisjoint(item.keys())


def test_supplier_order_view_exposes_delivery_address_only_when_verified(api_client, db):
    supplier_a, _ = _make_suppliers(db)
    order = _make_sendable_order(db, supplier=supplier_a, employee_id="emp-portal-addr")
    order.delivery_address_line1 = "12 Test Lane"
    order.delivery_city = "Colombo"
    db.commit()

    resp = api_client.get("/api/birthday/portal/orders", headers=supplier_headers_for(db, supplier_a))
    item = resp.json()["items"][0]
    assert item["address_verified"] is True
    assert item["delivery_address_line1"] == "12 Test Lane"
    assert item["delivery_city"] == "Colombo"


def test_supplier_order_view_hides_delivery_address_when_not_verified(api_client, db):
    supplier_a, _ = _make_suppliers(db)
    order = _make_sendable_order(db, supplier=supplier_a, employee_id="emp-portal-unverified")
    order.address_verification_status = "NEEDS_UPDATE"
    order.delivery_address_line1 = "12 Test Lane"
    order.delivery_city = "Colombo"
    db.commit()
    db.refresh(order)

    from app.services.order_service import to_supplier_view

    view = to_supplier_view(order)
    assert view.address_verified is False
    assert view.delivery_address_line1 is None
    assert view.delivery_city is None


def test_accept_merges_acknowledge_and_confirm(api_client, db):
    """Plan §O: the old two-step acknowledge-then-confirm is merged into
    one Accept action — SENT_TO_SUPPLIER goes straight to CONFIRMED."""
    supplier_a, _ = _make_suppliers(db)
    order = _make_sendable_order(db, supplier=supplier_a, employee_id="emp-portal-7")
    headers = supplier_headers_for(db, supplier_a)

    accept = api_client.post(f"/api/birthday/portal/orders/{order.id}/accept", headers=headers)
    assert accept.status_code == 200
    assert accept.json()["status"] == "CONFIRMED"

    # A supplier may not jump straight to COMPLETED.
    blocked = api_client.patch(
        f"/api/birthday/portal/orders/{order.id}/status", json={"status": "COMPLETED"}, headers=headers,
    )
    assert blocked.status_code == 409


def test_delivered_auto_completes(api_client, db):
    """Plan §F/§L: DELIVERED -> COMPLETED happens automatically, no
    internal action required."""
    supplier_a, _ = _make_suppliers(db)
    order = _make_sendable_order(db, supplier=supplier_a, employee_id="emp-portal-autocomplete")
    order.status = "OUT_FOR_DELIVERY"
    db.commit()
    headers = supplier_headers_for(db, supplier_a)

    resp = api_client.patch(
        f"/api/birthday/portal/orders/{order.id}/status", json={"status": "DELIVERED"}, headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "COMPLETED"


def test_raise_issue_notifies_admin(api_client, db, platform_calls):
    supplier_a, _ = _make_suppliers(db)
    order = _make_sendable_order(db, supplier=supplier_a, employee_id="emp-portal-8")
    headers = supplier_headers_for(db, supplier_a)

    resp = api_client.post(
        f"/api/birthday/portal/orders/{order.id}/issues",
        json={"type": "DELIVERY_ISSUE", "detail": "Out of stock for this cake size"},
        headers=headers,
    )
    assert resp.status_code == 201
    assert len(platform_calls["broadcasts"]) == 1
    assert platform_calls["broadcasts"][0]["role"] == "BIRTHDAY_ADMIN"


def test_cannot_fulfil_issue_flips_status(api_client, db):
    supplier_a, _ = _make_suppliers(db)
    order = _make_sendable_order(db, supplier=supplier_a, employee_id="emp-portal-cannotfulfil")
    headers = supplier_headers_for(db, supplier_a)

    resp = api_client.post(
        f"/api/birthday/portal/orders/{order.id}/issues",
        json={"type": "CANNOT_FULFIL", "detail": "Oven is down"},
        headers=headers,
    )
    assert resp.status_code == 201

    detail = api_client.get(f"/api/birthday/portal/orders/{order.id}", headers=headers).json()
    assert detail["status"] == "UNABLE_TO_FULFIL"


def test_issue_cannot_be_raised_on_terminal_order(api_client, db):
    """A supplier can only raise an issue while the order is still in
    progress — not after it is DELIVERED (or cancelled/completed)."""
    supplier_a, _ = _make_suppliers(db)
    order = _make_sendable_order(db, supplier=supplier_a, employee_id="emp-portal-terminal")
    order.status = "DELIVERED"
    db.commit()
    headers = supplier_headers_for(db, supplier_a)

    resp = api_client.post(
        f"/api/birthday/portal/orders/{order.id}/issues",
        json={"type": "OTHER", "detail": "too late now"},
        headers=headers,
    )
    assert resp.status_code == 409


def test_pending_verification_order_not_visible_to_supplier(api_client, db):
    """An order still awaiting the internal address-verification
    checkpoint (not yet released) must never be visible in the supplier
    portal."""
    from app.models.birthday_order import BirthdayOrder
    from app.models.supplier import Supplier

    supplier = Supplier(name="Pending Visibility Supplier", primary_contact_email="dv@supplier.example.com")
    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    order = BirthdayOrder(
        order_reference="BDAY-EMPdv-2026-00001",
        employee_id="emp-dv",
        employee_name="Pending Visibility",
        employee_email="dv@example.com",
        birthday_date=date.today() + timedelta(days=10),
        birthday_year=(date.today() + timedelta(days=10)).year,
        office_location="Colombo",
        status="PENDING_VERIFICATION",
        supplier_id=supplier.id,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    resp = api_client.get(
        f"/api/birthday/portal/orders/{order.id}", headers=supplier_headers_for(db, supplier),
    )
    assert resp.status_code == 404


def test_cancelled_order_shows_as_tombstone_not_404(api_client, db):
    """Plan §Y: internal->supplier changes must not be silent. A cancelled
    order stays visible in the portal with its CANCELLED status instead
    of vanishing."""
    supplier_a, _ = _make_suppliers(db)
    order = _make_sendable_order(db, supplier=supplier_a, employee_id="emp-portal-cancel-tombstone")
    order.status = "CANCELLED"
    db.commit()

    resp = api_client.get(
        f"/api/birthday/portal/orders/{order.id}", headers=supplier_headers_for(db, supplier_a),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"


def test_internal_user_cannot_use_supplier_portal_routes(api_client, db):
    resp = api_client.get("/api/birthday/portal/orders", headers=headers_for(108, role="BIRTHDAY_ADMIN"))
    assert resp.status_code == 403
