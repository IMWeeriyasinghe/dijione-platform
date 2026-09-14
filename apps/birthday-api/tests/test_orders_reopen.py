"""Phase 1.6 §14 — the dedicated, non-bypassable Reopen command.

Central review correction: CANCELLED must stay mapped to ``set()`` in
``order_status_service.ALLOWED_TRANSITIONS`` for every caller EXCEPT
``reopen_cancelled_order`` itself — the generic ``transition()`` path must
keep rejecting a raw ``CANCELLED -> *`` call, even after a real reopen
capability exists elsewhere.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.core.constants import ActorType, ExceptionReason, OrderStatus
from app.services import order_status_service
from tests.conftest import headers_for


def _order(db, *, status=OrderStatus.CANCELLED.value, supplier_id=None, catalogue_item_id=None,
           employee_id="reopen-emp-1", released_at=None):
    from app.models.birthday_order import BirthdayOrder

    order = BirthdayOrder(
        order_reference=f"BDAY-EMP{employee_id}-2026-00001",
        employee_id=employee_id,
        employee_number="4242",
        employee_name="Reopen Person",
        employee_email="reopen@example.com",
        birthday_date=date.today() + timedelta(days=20),
        birthday_year=(date.today() + timedelta(days=20)).year,
        office_location="Colombo",
        quantity=1,
        status=status,
        supplier_id=supplier_id,
        catalogue_item_id=catalogue_item_id,
        delivery_date=date.today() + timedelta(days=19),
        address_verification_status="VERIFIED",
        released_at=released_at,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def _active_supplier(db):
    from app.models.supplier import Supplier

    s = Supplier(name="Reopen Bakery", primary_contact_email="reopen@bakery.example.com", status="ACTIVE")
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _catalogue_item(db, supplier, *, is_active=True):
    from app.models.supplier_catalogue_item import SupplierCatalogueItem

    item = SupplierCatalogueItem(supplier_id=supplier.id, name="Standard Sponge", is_active=is_active)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def test_reopen_never_reached_supplier_lands_pending_verification(api_client, db):
    supplier = _active_supplier(db)
    item = _catalogue_item(db, supplier)
    order = _order(db, supplier_id=supplier.id, catalogue_item_id=item.id, released_at=None)
    headers = headers_for(1, role="BIRTHDAY_ADMIN")

    resp = api_client.post(
        f"/api/birthday/orders/{order.id}/reopen", json={"reason": "Cancelled by mistake"}, headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == OrderStatus.PENDING_VERIFICATION.value
    assert body["exception_reason"] is None
    assert any(e["event_type"] == "REOPENED" for e in body["events"])


def test_reopen_never_reached_supplier_missing_supplier_lands_requires_attention(api_client, db):
    order = _order(db, supplier_id=None, catalogue_item_id=None, released_at=None)
    headers = headers_for(1, role="BIRTHDAY_ADMIN")

    resp = api_client.post(
        f"/api/birthday/orders/{order.id}/reopen", json={"reason": "test"}, headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == OrderStatus.REQUIRES_ATTENTION.value
    assert body["exception_reason"] == ExceptionReason.NO_SUPPLIER.value


def test_reopen_after_supplier_visibility_lands_requires_review(api_client, db):
    from datetime import UTC, datetime

    supplier = _active_supplier(db)
    item = _catalogue_item(db, supplier)
    order = _order(
        db, supplier_id=supplier.id, catalogue_item_id=item.id,
        released_at=datetime.now(UTC) - timedelta(days=2),
    )
    headers = headers_for(1, role="BIRTHDAY_ADMIN")

    resp = api_client.post(
        f"/api/birthday/orders/{order.id}/reopen", json={"reason": "Supplier says they can still do it"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == OrderStatus.REQUIRES_REVIEW.value


def test_reopen_rejects_non_cancelled_order(api_client, db):
    order = _order(db, status=OrderStatus.PENDING_VERIFICATION.value)
    headers = headers_for(1, role="BIRTHDAY_ADMIN")
    resp = api_client.post(
        f"/api/birthday/orders/{order.id}/reopen", json={"reason": "test"}, headers=headers,
    )
    assert resp.status_code == 409


def test_reopen_rejects_empty_reason(api_client, db):
    order = _order(db)
    headers = headers_for(1, role="BIRTHDAY_ADMIN")
    resp = api_client.post(
        f"/api/birthday/orders/{order.id}/reopen", json={"reason": "   "}, headers=headers,
    )
    assert resp.status_code == 409


def test_reopen_rejects_when_completed_order_exists_for_employee_year(api_client, db):
    from app.models.birthday_order import BirthdayOrder

    order = _order(db, employee_id="dup-emp")
    completed = BirthdayOrder(
        order_reference="BDAY-EMPdup-emp-2026-00002",
        employee_id="dup-emp",
        employee_number="4242",
        employee_name="Reopen Person",
        employee_email="reopen@example.com",
        birthday_date=order.birthday_date,
        birthday_year=order.birthday_year,
        office_location="Colombo",
        status=OrderStatus.COMPLETED.value,
    )
    # bypass the unique constraint deliberately impossible in real life —
    # simulate a data anomaly to prove the defensive re-check fires.
    db.add(completed)
    try:
        db.commit()
    except Exception:
        db.rollback()
        pytest.skip("DB enforces the unique constraint before the app-level check can run")

    headers = headers_for(1, role="BIRTHDAY_ADMIN")
    resp = api_client.post(
        f"/api/birthday/orders/{order.id}/reopen", json={"reason": "test"}, headers=headers,
    )
    assert resp.status_code == 409


def test_reopen_requires_permission(api_client, db):
    order = _order(db)
    headers = headers_for(1, role="BIRTHDAY_USER")
    resp = api_client.post(
        f"/api/birthday/orders/{order.id}/reopen", json={"reason": "test"}, headers=headers,
    )
    assert resp.status_code == 403


def test_generic_transition_still_rejects_cancelled_to_anything(db):
    """The core safety property this review demanded: ALLOWED_TRANSITIONS
    stays set() for CANCELLED — a caller reaching for the ordinary
    transition() function (bypassing reopen_cancelled_order and every one
    of its eligibility checks) must still be rejected."""
    order = _order(db)
    with pytest.raises(order_status_service.InvalidTransitionError):
        order_status_service.transition(
            db, order, OrderStatus.PENDING_VERIFICATION,
            actor_id=1, actor_type=ActorType.USER, detail="illegitimate bypass attempt",
        )


def test_reopen_clears_stale_inactive_supplier_and_catalogue_item(api_client, db):
    supplier = _active_supplier(db)
    item = _catalogue_item(db, supplier, is_active=False)
    supplier.status = "INACTIVE"
    db.commit()
    order = _order(db, supplier_id=supplier.id, catalogue_item_id=item.id, released_at=None)
    headers = headers_for(1, role="BIRTHDAY_ADMIN")

    resp = api_client.post(
        f"/api/birthday/orders/{order.id}/reopen", json={"reason": "test"}, headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["supplier_id"] is None
    assert body["catalogue_item_id"] is None
    assert body["status"] == OrderStatus.REQUIRES_ATTENTION.value
    assert body["exception_reason"] == ExceptionReason.NO_SUPPLIER.value
