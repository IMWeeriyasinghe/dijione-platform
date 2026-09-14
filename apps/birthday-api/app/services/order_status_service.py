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

from sqlalchemy import select
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

# The subset of transitions a supplier-portal user may drive directly — the
# forward fulfilment progression only. "I need a change" and "I can't fulfil
# this" are NOT status buttons any more (Phase 1 §V.1): both go through the
# structured "Report a problem" action, which creates a typed OrderIssue;
# only CANNOT_FULFIL then also moves the order (-> UNABLE_TO_FULFIL, handled
# in the portal issues route, not here). One path per intent.
SUPPLIER_DRIVABLE: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.SENT_TO_SUPPLIER: {OrderStatus.CONFIRMED},
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

# Phase 1.6 §12/§18-review-correction-1: communication eligibility is a
# DIFFERENT business concept from "is this order's fulfilment settled"
# (birthday_order_repository._TERMINAL_STATUSES, used for due/dashboard
# calculations). Only COMPLETED and CANCELLED close the conversation — a
# DELIVERED order auto-completes almost immediately so no special rule is
# introduced for it, and UNABLE_TO_FULFIL deliberately stays OPEN because
# operations and the supplier still need to discuss reassignment/recovery.
# Do not reuse the fulfilment _TERMINAL_STATUSES for this guard.
SUPPLIER_COMMUNICATION_CLOSED_STATUSES: frozenset[str] = frozenset(
    {OrderStatus.COMPLETED.value, OrderStatus.CANCELLED.value}
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


def _apply_transition(
    db: Session,
    order: BirthdayOrder,
    from_status: OrderStatus,
    to_status: OrderStatus,
    *,
    actor_id: int | None,
    actor_type: ActorType,
    detail: str | None = None,
    event_type: str = "STATUS_CHANGE",
    audit_service: AuditService | None = None,
    audit_action: str = "birthday.order.status_change",
    actor_display_name: str | None = None,
) -> BirthdayOrder:
    """The actual mutation + OrderEvent + audit write — no gating logic of
    its own. Private: callers must go through either ``transition()`` (the
    normal, ALLOWED_TRANSITIONS-checked path every ordinary caller uses) or
    ``reopen_cancelled_order()`` (the one deliberate, fully-guarded
    exception — Phase 1.6 §14). Never call this directly from a route."""
    order.status = to_status.value
    db.add(
        OrderEvent(
            order_id=order.id,
            event_type=event_type,
            from_status=from_status.value,
            to_status=to_status.value,
            actor_id=actor_id,
            actor_type=actor_type.value,
            actor_display_name=actor_display_name,
            detail=detail,
        )
    )
    db.flush()

    service = audit_service or AuditService()
    try:
        service.log(
            actor_id=actor_id,
            action=audit_action,
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
    actor_display_name: str | None = None,
) -> BirthdayOrder:
    """The single place every ordinary caller mutates ``BirthdayOrder.status``
    — gated by ``ALLOWED_TRANSITIONS``. ``ALLOWED_TRANSITIONS[CANCELLED]``
    and ``[COMPLETED]`` are both ``set()`` (fully terminal), so this
    function rejects *every* attempted transition out of either status,
    unconditionally, for every caller — including any future one. That is
    deliberate (Phase 1.6 §14 review correction #3): the only way a
    CANCELLED order ever moves again is ``reopen_cancelled_order()`` below,
    which does not call this function."""
    from_status = OrderStatus(order.status)
    allowed = ALLOWED_TRANSITIONS.get(from_status, set())
    if to_status not in allowed:
        raise InvalidTransitionError(from_status, to_status)
    return _apply_transition(
        db, order, from_status, to_status,
        actor_id=actor_id, actor_type=actor_type, detail=detail,
        event_type=event_type, audit_service=audit_service,
        actor_display_name=actor_display_name,
    )


def hold(
    db: Session, order: BirthdayOrder, *, hold_reason: str, actor_id: int | None,
    audit_service: AuditService | None = None, actor_display_name: str | None = None,
) -> BirthdayOrder:
    order.hold_reason = hold_reason
    return transition(
        db, order, OrderStatus.ON_HOLD,
        actor_id=actor_id, actor_type=ActorType.USER, detail=hold_reason,
        audit_service=audit_service, actor_display_name=actor_display_name,
    )


def release(
    db: Session, order: BirthdayOrder, *, actor_id: int | None, note: str | None = None,
    audit_service: AuditService | None = None,
    to_status: OrderStatus = OrderStatus.PENDING_VERIFICATION,
    actor_display_name: str | None = None,
) -> BirthdayOrder:
    """Releases a held order back into the normal flow. Defaults to
    PENDING_VERIFICATION (not the legacy PLANNED status — that bug is
    fixed here)."""
    order.hold_reason = None
    return transition(
        db, order, to_status,
        actor_id=actor_id, actor_type=ActorType.USER, detail=note,
        audit_service=audit_service, actor_display_name=actor_display_name,
    )


def cancel(
    db: Session, order: BirthdayOrder, *, actor_id: int | None, reason: str | None = None,
    audit_service: AuditService | None = None, actor_display_name: str | None = None,
) -> BirthdayOrder:
    return transition(
        db, order, OrderStatus.CANCELLED,
        actor_id=actor_id, actor_type=ActorType.USER, detail=reason,
        audit_service=audit_service, actor_display_name=actor_display_name,
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
        audit_service=audit_service, actor_display_name="System",
    )


class ReopenNotEligibleError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def order_was_released_to_supplier(order: BirthdayOrder) -> bool:
    """Phase 1.6 §14 (review correction #2) — the authoritative "did this
    order ever reach the supplier" signal, used by ``reopen_cancelled_order``
    to decide the Reopen target state. ``released_at`` is written exactly
    once, at release time (``address_verification_service.verify_and_release``
    / ``confirm_release``), and is never cleared afterwards — ``cancel()``
    does not touch it — so it still reads true after a later cancellation,
    which is exactly the historical fact needed here.

    Deliberately NOT "any SupplierCommunication row exists for this order":
    that store is the unified communication log and can carry internal/
    system rows too, which would over-broaden what "reached the supplier"
    means.
    """
    return order.released_at is not None


def reopen_cancelled_order(
    db: Session,
    order: BirthdayOrder,
    *,
    reason: str,
    actor_id: int,
    audit_service: AuditService | None = None,
    actor_display_name: str | None = None,
) -> BirthdayOrder:
    """Dedicated, non-bypassable Reopen command (Phase 1.6 §14). Deliberately
    does **not** go through ``transition()``/``ALLOWED_TRANSITIONS`` —
    ``CANCELLED`` stays mapped to ``set()`` there, fully terminal, for every
    other caller. This is the one function that may move an order out of
    CANCELLED, and only once every eligibility check below has passed.
    """
    from app.core.constants import ExceptionReason
    from app.models.supplier import Supplier
    from app.models.supplier_catalogue_item import SupplierCatalogueItem
    from app.services import readiness_service

    current = OrderStatus(order.status)
    if current != OrderStatus.CANCELLED:
        raise InvalidTransitionError(current, OrderStatus.PENDING_VERIFICATION)
    if not reason or not reason.strip():
        raise ReopenNotEligibleError("A reason is required to reopen a cancelled order")

    # Defensive re-check: the DB UniqueConstraint(employee_id, birthday_year)
    # already prevents a second row, but confirm no completed/delivered
    # fulfilment exists for this employee/year before reopening this one.
    existing = db.execute(
        select(BirthdayOrder).where(
            BirthdayOrder.employee_id == order.employee_id,
            BirthdayOrder.birthday_year == order.birthday_year,
            BirthdayOrder.id != order.id,
            BirthdayOrder.status.in_([OrderStatus.COMPLETED.value, OrderStatus.DELIVERED.value]),
        )
    ).scalars().first()
    if existing is not None:
        raise ReopenNotEligibleError(
            "A completed/delivered order already exists for this employee's "
            f"birthday this year: {existing.order_reference}"
        )

    # Supplier/catalogue validity — clear a stale assignment rather than
    # silently keeping it; readiness below then correctly re-flags it.
    if order.supplier_id is not None:
        supplier = db.get(Supplier, order.supplier_id)
        if supplier is None or supplier.status != "ACTIVE":
            order.supplier_id = None
    if order.catalogue_item_id is not None:
        item = db.get(SupplierCatalogueItem, order.catalogue_item_id)
        if item is None or not item.is_active:
            order.catalogue_item_id = None

    if order_was_released_to_supplier(order):
        # Never silently resumed — a human must deliberately confirm-release
        # again, which always generates a fresh outbound communication, so
        # the supplier gets a real "this order is back on" signal instead of
        # an assumption their earlier acceptance/cancellation still applies.
        target = OrderStatus.REQUIRES_REVIEW
    else:
        result = readiness_service.check(order)
        if result.ready:
            target = OrderStatus.PENDING_VERIFICATION
            order.exception_reason = None
        else:
            target = OrderStatus.REQUIRES_ATTENTION
            if order.supplier_id is None:
                order.exception_reason = ExceptionReason.NO_SUPPLIER.value
            elif order.catalogue_item_id is None:
                order.exception_reason = ExceptionReason.NO_DEFAULT_CAKE.value

    return _apply_transition(
        db, order, OrderStatus.CANCELLED, target,
        actor_id=actor_id, actor_type=ActorType.USER,
        detail=reason, event_type="REOPENED",
        audit_service=audit_service, audit_action="birthday.order.reopen",
        actor_display_name=actor_display_name,
    )
