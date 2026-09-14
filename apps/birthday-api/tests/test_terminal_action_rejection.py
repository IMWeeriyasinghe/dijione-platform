"""Phase 1.6 §7/§10/§12 — terminal-order action rejection, both sides.

Pins the backend contract the frontend policy helpers (OrderDetail's
orderActionPolicy, the supplier portal's supplierActionPolicy) depend on,
so a future frontend refactor can't silently regress what the server
actually enforces.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.core.constants import ActorType, OrderStatus
from app.services import communication_service
from tests.conftest import headers_for, supplier_headers_for


def _order(db, *, status, supplier_id=None):
    from app.models.birthday_order import BirthdayOrder

    order = BirthdayOrder(
        order_reference=f"BDAY-EMPterm-{status}-2026-00001",
        employee_id=f"term-{status}",
        employee_name="Terminal Person",
        employee_email="terminal@example.com",
        birthday_date=date.today() + timedelta(days=20),
        birthday_year=(date.today() + timedelta(days=20)).year,
        office_location="Colombo",
        quantity=1,
        status=status,
        supplier_id=supplier_id,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@pytest.mark.parametrize("status", ["COMPLETED", "CANCELLED", "DELIVERED"])
def test_hold_rejected_on_terminal_orders(api_client, db, status):
    order = _order(db, status=status)
    headers = headers_for(1, role="BIRTHDAY_ADMIN")
    resp = api_client.post(
        f"/api/birthday/orders/{order.id}/hold", json={"hold_reason": "x"}, headers=headers,
    )
    assert resp.status_code == 409


def _supplier():
    from app.models.supplier import Supplier

    return Supplier(name="Terminal Bakery", primary_contact_email="terminal@bakery.example.com")


def test_supplier_message_rejected_on_completed_order(api_client, db):
    supplier = _supplier()
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    order = _order(db, status="COMPLETED", supplier_id=supplier.id)
    resp = api_client.post(
        f"/api/birthday/portal/orders/{order.id}/messages",
        json={"body": "hello"}, headers=supplier_headers_for(db, supplier),
    )
    assert resp.status_code == 409


def test_supplier_message_rejected_on_cancelled_order(api_client, db):
    supplier = _supplier()
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    order = _order(db, status="CANCELLED", supplier_id=supplier.id)
    resp = api_client.post(
        f"/api/birthday/portal/orders/{order.id}/messages",
        json={"body": "hello"}, headers=supplier_headers_for(db, supplier),
    )
    assert resp.status_code == 409


def test_supplier_message_allowed_on_unable_to_fulfil_order(api_client, db):
    """Review correction #1: UNABLE_TO_FULFIL deliberately stays OPEN for
    communication — operations and the supplier still need to discuss
    reassignment/recovery. Only COMPLETED/CANCELLED close it."""
    supplier = _supplier()
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    order = _order(db, status="UNABLE_TO_FULFIL", supplier_id=supplier.id)
    resp = api_client.post(
        f"/api/birthday/portal/orders/{order.id}/messages",
        json={"body": "Can we reassign this to another supplier?"},
        headers=supplier_headers_for(db, supplier),
    )
    assert resp.status_code == 201


def test_internal_message_still_allowed_on_completed_order(api_client, db):
    """The guard is scoped to author_type==SUPPLIER only — internal staff
    may still post a closing note on a completed order (review correction #1;
    not in the internal terminal-action matrix's disabled-actions list)."""
    supplier = _supplier()
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    order = _order(db, status="COMPLETED", supplier_id=supplier.id)
    headers = headers_for(1, role="BIRTHDAY_ADMIN")
    resp = api_client.post(
        f"/api/birthday/orders/{order.id}/messages",
        json={"body": "Closing this out, thanks all"}, headers=headers,
    )
    assert resp.status_code == 201


def test_communication_service_raises_typed_error_directly():
    """Unit-level pin of the guard itself, independent of the HTTP layer."""
    from unittest.mock import MagicMock

    order = MagicMock(status=OrderStatus.CANCELLED.value)
    with pytest.raises(communication_service.CommunicationClosedError):
        communication_service.post_portal_message(
            MagicMock(), order, author_type=ActorType.SUPPLIER, author_id=1, body="hi",
        )
