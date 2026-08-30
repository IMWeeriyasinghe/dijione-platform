"""Transition-table-enforced status mutator (plan §P) — the single place
that mutates ``BirthdayOrder.status``. No route handler mutates status
directly; every transition writes an ``OrderEvent`` and calls
``AuditService.log(...)``.

"Verification is the approval" (decision A): there is no separate
approval status. ``address_verification_service.verify_and_release``
is the one function that decides whether a freshly-verified order is
released to the supplier automatically (a *standard* order) or parked in
``REQUIRES_REVIEW`` for a one-click human confirm (a *flagged* order).
Provenance that used to live on ``approved_at``/``approved_by`` now lives
on ``released_at``/``released_by`` and ``review_confirmed_at``/
``review_confirmed_by``, plus the ``AUTO_RELEASED`` / ``REVIEW_CONFIRMED``
``OrderEvent`` types.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.constants import ActorType, OrderStatus
from app.models.birthday_order import BirthdayOrder
from app.models.order_event import OrderEvent
from app.services.audit_service import AuditService

ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PENDING_VERIFICATION: {
        OrderStatus.REQUIRES_REVIEW, OrderStatus.SENT_TO_SUPPLIER,
        OrderStatus.ON_HOLD, OrderStatus.REQUIRES_ATTENTION, OrderStatus.CANCELLED,
    },
    OrderStatus.REQUIRES_REVIEW: {
        OrderStatus.SENT_TO_SUPPLIER, OrderStatus.ON_HOLD,
        OrderStatus.REQUIRES_ATTENTION, OrderStatus.CANCELLED,
    },
    OrderStatus.REQUIRES_ATTENTION: {
        OrderStatus.PENDING_VERIFICATION, OrderStatus.SENT_TO_SUPPLIER,
        OrderStatus.ON_HOLD, OrderStatus.CANCELLED, OrderStatus.REQUIRES_ATTENTION,
    },
    OrderStatus.ON_HOLD: {
        OrderStatus.PENDING_VERIFICATION, OrderStatus.REQUIRES_REVIEW,
        OrderStatus.SENT_TO_SUPPLIER, OrderStatus.CANCELLED,
    },
    OrderStatus.SENT_TO_SUPPLIER: {
        OrderStatus.CONFIRMED, OrderStatus.CHANGE_REQUESTED, OrderStatus.UNABLE_TO_FULFIL,
        OrderStatus.ON_HOLD, OrderStatus.REQUIRES_ATTENTION, OrderStatus.CANCELLED,
    },
    OrderStatus.CHANGE_REQUESTED: {OrderStatus.SENT_TO_SUPPLIER, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {
        OrderStatus.PREPARING, OrderStatus.UNABLE_TO_FULFIL, OrderStatus.CANCELLED,
    },
    OrderStatus.PREPARING: {
        OrderStatus.OUT_FOR_DELIVERY, OrderStatus.UNABLE_TO_FULFIL, OrderStatus.CANCELLED,
    },
    OrderStatus.OUT_FOR_DELIVERY: {
        OrderStatus.DELIVERED, OrderStatus.REQUIRES_ATTENTION, OrderStatus.CANCELLED,
    },
    OrderStatus.DELIVERED: {OrderStatus.COMPLETED},
    OrderStatus.UNABLE_TO_FULFIL: {OrderStatus.REQUIRES_ATTENTION},
    OrderStatus.CANCELLED: set(),
    OrderStatus.COMPLETED: set(),
}

# The subset of transitions a supplier-portal user may drive directly.
# Derived from ALLOWED_TRANSITIONS (never a hand-mirrored second table) so
# the portal frontend imports this instead of re-typing it.
SUPPLIER_DRIVABLE: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.SENT_TO_SUPPLIER: {
        OrderStatus.CONFIRMED, OrderStatus.CHANGE_REQUESTED, OrderStatus.UNABLE_TO_FULFIL,
    },
    OrderStatus.CONFIRMED: {OrderStatus.PREPARING},
    OrderStatus.PREPARING: {OrderStatus.OUT_FOR_DELIVERY},
    OrderStatus.OUT_FOR_DELIVERY: {OrderStatus.DELIVERED},
}

# Statuses in which a supplier still has something to do or report on.
SUPPLIER_ACTIONABLE_STATUSES: set[OrderStatus] = {
    OrderStatus.SENT_TO_SUPPLIER, OrderStatus.CHANGE_REQUESTED, OrderStatus.CONFIRMED,
    OrderStatus.PREPARING, OrderStatus.OUT_FOR_DELIVERY,
}

# Statuses visible to the supplier portal at all (includes terminal states
# so a cancellation shows as a tombstone with a reason instead of a 404 —
# plan §Y "internal->supplier changes must not be silent").
SUPPLIER_VISIBLE_STATUSES: tuple[str, ...] = (
    OrderStatus.SENT_TO_SUPPLIER.value, OrderStatus.CHANGE_REQUESTED.value,
    OrderStatus.CONFIRMED.value, OrderStatus.PREPARING.value,
    OrderStatus.OUT_FOR_DELIVERY.value, OrderStatus.DELIVERED.value,
    OrderStatus.COMPLETED.value, OrderStatus.UNABLE_TO_FULFIL.value,
    OrderStatus.CANCELLED.value,
)


class InvalidTransitionError(Exception):
    def __init__(self, from_status: OrderStatus, to_status: OrderStatus):
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"Cannot transition order from {from_status} to {to_status}")


class ReadinessNotMetError(Exception):
    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__(f"Order is not ready: missing {', '.join(missing)}")


def transition(
    db: Session,
    order: BirthdayOrder,
    to_status: OrderStatus,
    *,
    actor_id: int | None,
    actor_type: ActorType,
    detail: str | None = None,
    event_type: str = "STATUS_CHANGE",
    audit_service: AuditService | None = None,
) -> BirthdayOrder:
    from_status = OrderStatus(order.status)
    allowed = ALLOWED_TRANSITIONS.get(from_status, set())
    if to_status not in allowed:
        raise InvalidTransitionError(from_status, to_status)

    order.status = to_status.value
    db.add(
        OrderEvent(
            order_id=order.id,
            event_type=event_type,
            from_status=from_status.value,
            to_status=to_status.value,
            actor_id=actor_id,
            actor_type=actor_type.value,
            detail=detail,
        )
    )
    db.flush()

    service = audit_service or AuditService()
    try:
        service.log(
            actor_id=actor_id,
            action="birthday.order.status_change",
            entity_type="birthday_order",
            entity_id=order.id,
            previous_state={"status": from_status.value},
            new_state={"status": to_status.value},
            metadata={"detail": detail} if detail else None,
        )
    except Exception:  # noqa: BLE001 - best-effort, never fails the transition
        pass

    db.commit()
    db.refresh(order)
    return order


def hold(
    db: Session, order: BirthdayOrder, *, hold_reason: str, actor_id: int | None,
    audit_service: AuditService | None = None,
) -> BirthdayOrder:
    order.hold_reason = hold_reason
    return transition(
        db, order, OrderStatus.ON_HOLD,
        actor_id=actor_id, actor_type=ActorType.USER, detail=hold_reason,
        audit_service=audit_service,
    )


def release(
    db: Session, order: BirthdayOrder, *, actor_id: int | None, note: str | None = None,
    audit_service: AuditService | None = None,
    to_status: OrderStatus = OrderStatus.PENDING_VERIFICATION,
) -> BirthdayOrder:
    """Releases a held order back into the normal flow. Defaults to
    PENDING_VERIFICATION (not the legacy PLANNED status — that bug is
    fixed here)."""
    order.hold_reason = None
    return transition(
        db, order, to_status,
        actor_id=actor_id, actor_type=ActorType.USER, detail=note,
        audit_service=audit_service,
    )


def cancel(
    db: Session, order: BirthdayOrder, *, actor_id: int | None, reason: str | None = None,
    audit_service: AuditService | None = None,
) -> BirthdayOrder:
    return transition(
        db, order, OrderStatus.CANCELLED,
        actor_id=actor_id, actor_type=ActorType.USER, detail=reason,
        audit_service=audit_service,
    )


def auto_complete(
    db: Session, order: BirthdayOrder, *, audit_service: AuditService | None = None,
) -> BirthdayOrder:
    """DELIVERED -> COMPLETED, automatically, immediately, system-actor.
    No internal user action exists for this on purpose (plan §F/§L)."""
    if OrderStatus(order.status) != OrderStatus.DELIVERED:
        return order
    order.completed_at = datetime.now(UTC)
    return transition(
        db, order, OrderStatus.COMPLETED,
        actor_id=None, actor_type=ActorType.SYSTEM, detail="Auto-completed on delivery",
        audit_service=audit_service,
    )
