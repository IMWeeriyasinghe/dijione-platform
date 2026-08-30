"""order_status_service transition-table enforcement (semi-automation
future-state plan §P)."""

from datetime import date

import pytest

from app.core.constants import ActorType, OrderStatus
from app.models.birthday_order import BirthdayOrder
from app.services import order_status_service


def _order(db, status: OrderStatus = OrderStatus.PENDING_VERIFICATION) -> BirthdayOrder:
    order = BirthdayOrder(
        order_reference=f"BDAY-EMP1-{date.today().year}-00001",
        employee_id="1",
        employee_name="Test Employee",
        employee_email="test@example.com",
        birthday_date=date.today(),
        birthday_year=date.today().year,
        office_location="Colombo",
        status=status.value,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def test_valid_transition_pending_verification_to_sent_to_supplier(db):
    order = _order(db, OrderStatus.PENDING_VERIFICATION)
    updated = order_status_service.transition(
        db, order, OrderStatus.SENT_TO_SUPPLIER, actor_id=1, actor_type=ActorType.USER,
    )
    assert updated.status == OrderStatus.SENT_TO_SUPPLIER.value
    assert any(e.event_type == "STATUS_CHANGE" for e in updated.events)


def test_invalid_transition_completed_to_pending_verification_raises(db):
    order = _order(db, OrderStatus.COMPLETED)
    with pytest.raises(order_status_service.InvalidTransitionError):
        order_status_service.transition(
            db, order, OrderStatus.PENDING_VERIFICATION, actor_id=1, actor_type=ActorType.USER,
        )


def test_invalid_transition_cancelled_is_terminal(db):
    order = _order(db, OrderStatus.CANCELLED)
    with pytest.raises(order_status_service.InvalidTransitionError):
        order_status_service.transition(
            db, order, OrderStatus.PENDING_VERIFICATION, actor_id=1, actor_type=ActorType.USER,
        )


def test_unable_to_fulfil_can_move_to_requires_attention(db):
    order = _order(db, OrderStatus.UNABLE_TO_FULFIL)
    updated = order_status_service.transition(
        db, order, OrderStatus.REQUIRES_ATTENTION, actor_id=1, actor_type=ActorType.USER,
    )
    assert updated.status == OrderStatus.REQUIRES_ATTENTION.value


def test_hold_writes_event_and_sets_reason(db):
    order = _order(db, OrderStatus.PENDING_VERIFICATION)
    updated = order_status_service.hold(db, order, hold_reason="Awaiting info", actor_id=1)
    assert updated.status == OrderStatus.ON_HOLD.value
    assert updated.hold_reason == "Awaiting info"
    assert any(e.event_type == "STATUS_CHANGE" and e.to_status == "ON_HOLD" for e in updated.events)


def test_release_returns_to_pending_verification_and_clears_reason(db):
    """Fixes the current-state bug where release() defaulted orders into
    the legacy PLANNED status."""
    order = _order(db, OrderStatus.ON_HOLD)
    order.hold_reason = "was on hold"
    db.commit()
    updated = order_status_service.release(db, order, actor_id=1, note="cleared")
    assert updated.status == OrderStatus.PENDING_VERIFICATION.value
    assert updated.hold_reason is None


def test_cancel_from_pending_verification(db):
    order = _order(db, OrderStatus.PENDING_VERIFICATION)
    updated = order_status_service.cancel(db, order, actor_id=1, reason="No longer needed")
    assert updated.status == OrderStatus.CANCELLED.value
    assert any(e.event_type == "STATUS_CHANGE" and e.to_status == "CANCELLED" for e in updated.events)


def test_auto_complete_on_delivered(db):
    order = _order(db, OrderStatus.DELIVERED)
    updated = order_status_service.auto_complete(db, order)
    assert updated.status == OrderStatus.COMPLETED.value
    assert updated.completed_at is not None
    assert any(e.actor_type == ActorType.SYSTEM.value and e.to_status == "COMPLETED" for e in updated.events)


def test_auto_complete_is_a_noop_off_delivered(db):
    order = _order(db, OrderStatus.CONFIRMED)
    updated = order_status_service.auto_complete(db, order)
    assert updated.status == OrderStatus.CONFIRMED.value
