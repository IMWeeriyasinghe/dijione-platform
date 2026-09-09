"""Phase 1 §1.4 — Communication subsystem: bidirectional Portal messaging,
one SupplierCommunication store, one audience-filtered Unified Timeline.
"""

from __future__ import annotations

from datetime import date, timedelta

from tests.conftest import headers_for, supplier_headers_for


def _released_order(api_client, db):
    """An order already SENT_TO_SUPPLIER, plus internal admin + supplier
    headers scoped to the same supplier."""
    from app.models.supplier import Supplier

    supplier = Supplier(
        name="Comms Bakery", status="ACTIVE", is_default=True,
        primary_contact_email="comms@bakery.example.com", lead_time_days=3,
        working_days="Mon,Tue,Wed,Thu,Fri,Sat,Sun",
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    admin = headers_for(700, role="BIRTHDAY_ADMIN")
    payload = {
        "employee_id": "comms-1", "employee_number": "7100", "employee_name": "Comms Person",
        "employee_email": "comms.person@example.com",
        "birthday_date": str(date.today() + timedelta(days=15)),
        "office_location": "Colombo",
    }
    order = api_client.post("/api/birthday/orders", json=payload, headers=admin).json()
    oid = order["id"]
    api_client.patch(
        f"/api/birthday/orders/{oid}",
        json={"supplier_id": supplier.id, "delivery_date": str(date.today() + timedelta(days=14))},
        headers=admin,
    )
    v = api_client.post(f"/api/birthday/orders/{oid}/verify", json={}, headers=admin)
    assert v.json()["order"]["status"] == "SENT_TO_SUPPLIER"
    return oid, admin, supplier_headers_for(db, supplier)


def test_supplier_portal_message_reaches_internal_timeline(api_client, db):
    oid, admin, sup = _released_order(api_client, db)

    r = api_client.post(
        f"/api/birthday/portal/orders/{oid}/messages",
        json={"body": "Can you clarify the building number?"}, headers=sup,
    )
    assert r.status_code == 201, r.text
    entries = r.json()["entries"]
    assert any(e["kind"] == "message" and "building number" in (e["body"] or "") for e in entries)

    # internal sees it
    it = api_client.get(f"/api/birthday/orders/{oid}/timeline", headers=admin).json()
    msg = next(e for e in it["entries"] if e["kind"] == "message")
    assert msg["direction"] == "INBOUND"
    assert msg["author_type"] == "SUPPLIER"
    assert msg["channel"] == "Portal"


def test_internal_portal_message_reaches_supplier_timeline(api_client, db):
    oid, admin, sup = _released_order(api_client, db)

    r = api_client.post(
        f"/api/birthday/orders/{oid}/messages",
        json={"body": "Deliver to the 3rd floor reception."}, headers=admin,
    )
    assert r.status_code == 201, r.text

    st = api_client.get(f"/api/birthday/portal/orders/{oid}/timeline", headers=sup).json()
    msg = next(e for e in st["entries"] if e["kind"] == "message")
    assert msg["direction"] == "OUTBOUND"
    assert msg["author_type"] == "USER"
    assert "3rd floor" in msg["body"]


def test_no_auto_issue_from_a_portal_message(api_client, db):
    oid, admin, sup = _released_order(api_client, db)
    api_client.post(
        f"/api/birthday/portal/orders/{oid}/messages",
        json={"body": "Thanks, received."}, headers=sup,
    )
    issues = api_client.get(f"/api/birthday/orders/{oid}/issues", headers=admin).json()
    assert issues == []


def test_supplier_timeline_hides_internal_only_events(api_client, db):
    oid, admin, sup = _released_order(api_client, db)
    # internal-only activity: an address-verification note + an INTERNAL_NOTE
    api_client.post(
        f"/api/birthday/orders/{oid}/special-requirements",
        json={"kind": "INTERNAL_NOTE", "text": "call the office manager first"}, headers=admin,
    )
    api_client.patch(
        f"/api/birthday/orders/{oid}/address-verification",
        json={"status": "VERIFIED", "note": "confirmed with TM"}, headers=admin,
    )

    st = api_client.get(f"/api/birthday/portal/orders/{oid}/timeline", headers=sup).json()
    titles = " ".join(e["title"] for e in st["entries"])
    bodies = " ".join((e["body"] or "") for e in st["entries"])
    assert "Address Verification Change" not in titles
    assert "call the office manager" not in bodies
    # but the supplier DOES see lifecycle + the release email
    it = api_client.get(f"/api/birthday/orders/{oid}/timeline", headers=admin).json()
    assert any(e["title"] == "Address Verification Change" for e in it["entries"])


def test_supplier_change_request_is_an_issue_not_a_status(api_client, db):
    oid, admin, sup = _released_order(api_client, db)
    # accept first, then request a change
    api_client.post(f"/api/birthday/portal/orders/{oid}/accept", headers=sup)
    r = api_client.post(
        f"/api/birthday/portal/orders/{oid}/issues",
        json={"type": "CHANGE_REQUEST", "detail": "Need it a day earlier"}, headers=sup,
    )
    assert r.status_code == 201
    o = api_client.get(f"/api/birthday/portal/orders/{oid}", headers=sup).json()
    assert o["status"] == "CONFIRMED"  # unchanged — CHANGE_REQUEST does not move status

    # the old direct status path is gone
    bad = api_client.patch(
        f"/api/birthday/portal/orders/{oid}/status",
        json={"status": "CHANGE_REQUESTED"}, headers=sup,
    )
    assert bad.status_code == 409


def test_supplier_cannot_message_another_suppliers_order(api_client, db):
    oid, admin, _sup = _released_order(api_client, db)
    from app.models.supplier import Supplier

    other = Supplier(name="Other Bakery", primary_contact_email="other@bakery.example.com")
    db.add(other)
    db.commit()
    db.refresh(other)
    other_hdrs = supplier_headers_for(db, other)

    assert api_client.get(f"/api/birthday/portal/orders/{oid}/timeline", headers=other_hdrs).status_code == 404
    assert api_client.post(
        f"/api/birthday/portal/orders/{oid}/messages", json={"body": "hi"}, headers=other_hdrs
    ).status_code == 404
