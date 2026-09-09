"""Phase 1.5 §F/§G — the shared ``due`` delivery-window filter
(today | tomorrow | overdue) on the internal order list and the supplier
portal order list. Terminal orders are always excluded; an unknown value
is a 422.
"""

from __future__ import annotations

from datetime import date, timedelta

from tests.conftest import headers_for, supplier_headers_for


def _order(db, *, supplier=None, ref, status="PENDING_VERIFICATION", delivery_date, employee_id):
    from app.models.birthday_order import BirthdayOrder

    row = BirthdayOrder(
        order_reference=ref,
        employee_id=employee_id,
        employee_name="Due Filter Person",
        employee_email=f"{employee_id}@example.com",
        birthday_date=date.today() + timedelta(days=20),
        birthday_year=(date.today() + timedelta(days=20)).year,
        office_location="Colombo",
        quantity=1,
        status=status,
        supplier_id=supplier.id if supplier else None,
        delivery_date=delivery_date,
        address_verification_status="VERIFIED",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _supplier(db):
    from app.models.supplier import Supplier

    s = Supplier(name="Due Bakery", primary_contact_email="due@bakery.example.com")
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_internal_due_today_tomorrow_overdue(api_client, db):
    today = date.today()
    _order(db, ref="BDAY-EMP1-2026-00001", delivery_date=today, employee_id="due-today")
    _order(db, ref="BDAY-EMP2-2026-00002", delivery_date=today + timedelta(days=1), employee_id="due-tomorrow")
    _order(db, ref="BDAY-EMP3-2026-00003", delivery_date=today - timedelta(days=2), employee_id="due-overdue")
    _order(db, ref="BDAY-EMP4-2026-00004", delivery_date=today + timedelta(days=9), employee_id="due-later")
    # A settled order whose delivery date is *today* must not surface.
    _order(
        db, ref="BDAY-EMP5-2026-00005", delivery_date=today,
        status="DELIVERED", employee_id="due-delivered",
    )
    headers = headers_for(1, role="BIRTHDAY_USER")

    got_today = api_client.get("/api/birthday/orders", params={"due": "today"}, headers=headers).json()
    assert {i["order_reference"] for i in got_today["items"]} == {"BDAY-EMP1-2026-00001"}

    got_tomorrow = api_client.get("/api/birthday/orders", params={"due": "tomorrow"}, headers=headers).json()
    assert {i["order_reference"] for i in got_tomorrow["items"]} == {"BDAY-EMP2-2026-00002"}

    got_overdue = api_client.get("/api/birthday/orders", params={"due": "overdue"}, headers=headers).json()
    assert {i["order_reference"] for i in got_overdue["items"]} == {"BDAY-EMP3-2026-00003"}


def test_internal_due_rejects_unknown_value(api_client, db):
    resp = api_client.get(
        "/api/birthday/orders", params={"due": "yesterday"},
        headers=headers_for(1, role="BIRTHDAY_USER"),
    )
    assert resp.status_code == 422


def test_supplier_list_due_filter_is_scoped(api_client, db):
    today = date.today()
    supplier = _supplier(db)
    _order(
        db, supplier=supplier, ref="BDAY-EMP7-2026-00007", status="SENT_TO_SUPPLIER",
        delivery_date=today, employee_id="sup-due-today",
    )
    _order(
        db, supplier=supplier, ref="BDAY-EMP8-2026-00008", status="SENT_TO_SUPPLIER",
        delivery_date=today - timedelta(days=1), employee_id="sup-due-overdue",
    )

    resp = api_client.get(
        "/api/birthday/portal/orders", params={"due": "overdue"},
        headers=supplier_headers_for(db, supplier),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["order_reference"] == "BDAY-EMP8-2026-00008"


def test_supplier_list_status_filter_accepts_comma_list(api_client, db):
    today = date.today()
    supplier = _supplier(db)
    _order(
        db, supplier=supplier, ref="BDAY-EMP9-2026-00009", status="PREPARING",
        delivery_date=today + timedelta(days=2), employee_id="sup-preparing",
    )
    _order(
        db, supplier=supplier, ref="BDAY-EMP10-2026-00010", status="OUT_FOR_DELIVERY",
        delivery_date=today + timedelta(days=1), employee_id="sup-ofd",
    )
    _order(
        db, supplier=supplier, ref="BDAY-EMP11-2026-00011", status="SENT_TO_SUPPLIER",
        delivery_date=today + timedelta(days=3), employee_id="sup-sent",
    )

    resp = api_client.get(
        "/api/birthday/portal/orders",
        params={"status_filter": "PREPARING,OUT_FOR_DELIVERY"},
        headers=supplier_headers_for(db, supplier),
    )
    assert resp.status_code == 200
    refs = {i["order_reference"] for i in resp.json()["items"]}
    assert refs == {"BDAY-EMP9-2026-00009", "BDAY-EMP10-2026-00010"}
