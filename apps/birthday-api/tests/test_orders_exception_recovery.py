"""Phase 1.5 §H2 — a ``NO_SUPPLIER`` / ``NO_DEFAULT_CAKE`` exception must
clear itself once the operator assigns a supplier / cake through the
Fulfilment Assignment PATCH, so the order stops *looking* broken. A
REQUIRES_ATTENTION order whose only blocker was that exception moves back
to PENDING_VERIFICATION.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.core.constants import ExceptionReason, OrderStatus
from tests.conftest import headers_for


def _attention_order(db, *, exception_reason, catalogue_item_id=None):
    from app.models.birthday_order import BirthdayOrder

    order = BirthdayOrder(
        order_reference="BDAY-EMP4242-2026-00001",
        employee_id="rec-emp-1",
        employee_number="4242",
        employee_name="Recovery Person",
        employee_email="recovery@example.com",
        birthday_date=date.today() + timedelta(days=20),
        birthday_year=(date.today() + timedelta(days=20)).year,
        office_location="Colombo",
        quantity=1,
        status=OrderStatus.REQUIRES_ATTENTION.value,
        exception_reason=exception_reason,
        catalogue_item_id=catalogue_item_id,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def _active_supplier(db):
    from app.models.supplier import Supplier

    s = Supplier(name="Recovery Bakery", primary_contact_email="rec@bakery.example.com", status="ACTIVE")
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _catalogue_item(db, supplier):
    from app.models.supplier_catalogue_item import SupplierCatalogueItem

    item = SupplierCatalogueItem(supplier_id=supplier.id, name="Standard Sponge", is_active=True)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def test_no_supplier_exception_clears_on_supplier_assignment(api_client, db):
    supplier = _active_supplier(db)
    order = _attention_order(db, exception_reason=ExceptionReason.NO_SUPPLIER.value)
    headers = headers_for(1, role="BIRTHDAY_ADMIN")

    resp = api_client.patch(
        f"/api/birthday/orders/{order.id}",
        json={"supplier_id": supplier.id},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["exception_reason"] is None
    assert body["status"] == OrderStatus.PENDING_VERIFICATION.value

    events = api_client.get(f"/api/birthday/orders/{order.id}", headers=headers).json()["events"]
    assert any(e["event_type"] == "EXCEPTION_CLEARED" for e in events)


def test_no_default_cake_exception_clears_on_cake_assignment(api_client, db):
    supplier = _active_supplier(db)
    item = _catalogue_item(db, supplier)
    order = _attention_order(db, exception_reason=ExceptionReason.NO_DEFAULT_CAKE.value)
    # cake selection needs the supplier set too
    order.supplier_id = supplier.id
    db.commit()
    headers = headers_for(1, role="BIRTHDAY_ADMIN")

    resp = api_client.patch(
        f"/api/birthday/orders/{order.id}",
        json={"catalogue_item_id": item.id},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["exception_reason"] is None
    assert body["status"] == OrderStatus.PENDING_VERIFICATION.value


def test_exception_not_cleared_when_blocker_still_present(api_client, db):
    """PATCHing an unrelated field must NOT clear a NO_SUPPLIER exception
    while supplier_id is still null."""
    order = _attention_order(db, exception_reason=ExceptionReason.NO_SUPPLIER.value)
    headers = headers_for(1, role="BIRTHDAY_ADMIN")

    resp = api_client.patch(
        f"/api/birthday/orders/{order.id}",
        json={"delivery_date": str(date.today() + timedelta(days=15))},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["exception_reason"] == ExceptionReason.NO_SUPPLIER.value
    assert body["status"] == OrderStatus.REQUIRES_ATTENTION.value
