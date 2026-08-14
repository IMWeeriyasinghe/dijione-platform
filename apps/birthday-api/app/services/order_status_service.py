"""Transition-table-enforced status mutator (plan §5) — the single place
that mutates ``BirthdayOrder.status``. No route handler mutates status
directly; every transition writes an ``OrderEvent`` and calls
``AuditService.log(...)``.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.constants import ActorType, OrderStatus
from app.models.birthday_order import BirthdayOrder
from app.models.order_event import OrderEvent
from app.services.audit_service import AuditService

ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    # Approval workflow (Phase-Next §2). DRAFT is the default creation
    # status for both auto-detected and manual/ad hoc orders; only an
    # explicit human APPROVE action can produce APPROVED, and only
    # APPROVED (or REQUIRES_ATTENTION, for exception-recovery resends)
    # orders may be sent to a supplier — see order_email_service._send's
    # explicit status check, which is the real enforcement point (this
    # table alone would also permit REQUIRES_ATTENTION -> SENT_TO_SUPPLIER
    # for that reason).
    OrderStatus.DRAFT: {
        OrderStatus.READY_FOR_APPROVAL, OrderStatus.ON_HOLD, OrderStatus.CANCELLED,
    },
    OrderStatus.READY_FOR_APPROVAL: {
        OrderStatus.APPROVED, OrderStatus.REJECTED, OrderStatus.DRAFT,
        OrderStatus.ON_HOLD, OrderStatus.CANCELLED,
    },
    OrderStatus.APPROVED: {
        OrderStatus.SENT_TO_SUPPLIER, OrderStatus.ON_HOLD, OrderStatus.CANCELLED,
        OrderStatus.REQUIRES_ATTENTION,
    },
    OrderStatus.REJECTED: {
        OrderStatus.DRAFT, OrderStatus.CANCELLED, OrderStatus.REQUIRES_ATTENTION,
    },
    # REQUIRES_ATTENTION added (Phase D): a first send attempt failing while
    # the order is still PLANNED must be able to land in the exception
    # queue directly, not only via ON_HOLD.
    OrderStatus.PLANNED: {
        OrderStatus.ON_HOLD, OrderStatus.SENT_TO_SUPPLIER, OrderStatus.CANCELLED,
        OrderStatus.REQUIRES_ATTENTION,
    },
    OrderStatus.ON_HOLD: {
        OrderStatus.PLANNED, OrderStatus.DRAFT, OrderStatus.READY_FOR_APPROVAL,
        OrderStatus.APPROVED, OrderStatus.SENT_TO_SUPPLIER, OrderStatus.CANCELLED,
        OrderStatus.REQUIRES_ATTENTION,
    },
    OrderStatus.SENT_TO_SUPPLIER: {
        OrderStatus.SUPPLIER_REVIEW, OrderStatus.CONFIRMED, OrderStatus.CHANGE_REQUESTED,
        OrderStatus.REJECTED, OrderStatus.UNABLE_TO_FULFIL, OrderStatus.CANCELLED,
        OrderStatus.REQUIRES_ATTENTION,
    },
    OrderStatus.SUPPLIER_REVIEW: {
        OrderStatus.CONFIRMED, OrderStatus.CHANGE_REQUESTED, OrderStatus.REJECTED,
        OrderStatus.UNABLE_TO_FULFIL, OrderStatus.CANCELLED,
    },
    OrderStatus.CHANGE_REQUESTED: {OrderStatus.SENT_TO_SUPPLIER, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.PREPARING, OrderStatus.CANCELLED},
    OrderStatus.PREPARING: {OrderStatus.OUT_FOR_DELIVERY, OrderStatus.CANCELLED},
    OrderStatus.OUT_FOR_DELIVERY: {OrderStatus.DELIVERED, OrderStatus.CANCELLED},
    OrderStatus.DELIVERED: {OrderStatus.COMPLETED},
    # SENT_TO_SUPPLIER added (Phase D): a successful resend from the
    # exception queue must be able to move the order forward again.
    # Self-loop added: a repeated failed resend re-records the exception
    # without requiring an artificial escape through another status first.
    OrderStatus.REQUIRES_ATTENTION: {
        OrderStatus.PLANNED, OrderStatus.DRAFT, OrderStatus.READY_FOR_APPROVAL,
        OrderStatus.APPROVED, OrderStatus.ON_HOLD, OrderStatus.CANCELLED,
        OrderStatus.SENT_TO_SUPPLIER, OrderStatus.REQUIRES_ATTENTION,
    },
    OrderStatus.UNABLE_TO_FULFIL: {OrderStatus.REQUIRES_ATTENTION},
    OrderStatus.CANCELLED: set(),
    OrderStatus.COMPLETED: set(),
}


class InvalidTransitionError(Exception):
    def __init__(self, from_status: OrderStatus, to_status: OrderStatus):
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"Cannot transition order from {from_status} to {to_status}")


def transition(
    db: Session,
    order: BirthdayOrder,
    to_status: OrderStatus,
    *,
    actor_id: int | None,
    actor_type: ActorType,
    detail: str | None = None,
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
            event_type="STATUS_CHANGE",
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
    order = transition(
        db, order, OrderStatus.ON_HOLD,
        actor_id=actor_id, actor_type=ActorType.USER, detail=hold_reason,
        audit_service=audit_service,
    )
    return order


def release(
    db: Session, order: BirthdayOrder, *, actor_id: int | None, note: str | None = None,
    audit_service: AuditService | None = None, to_status: OrderStatus = OrderStatus.PLANNED,
) -> BirthdayOrder:
    order.hold_reason = None
    order = transition(
        db, order, to_status,
        actor_id=actor_id, actor_type=ActorType.USER, detail=note,
        audit_service=audit_service,
    )
    return order


def cancel(
    db: Session, order: BirthdayOrder, *, actor_id: int | None, reason: str | None = None,
    audit_service: AuditService | None = None,
) -> BirthdayOrder:
    return transition(
        db, order, OrderStatus.CANCELLED,
        actor_id=actor_id, actor_type=ActorType.USER, detail=reason,
        audit_service=audit_service,
    )


def submit_for_approval(
    db: Session, order: BirthdayOrder, *, actor_id: int | None,
    audit_service: AuditService | None = None,
) -> BirthdayOrder:
    """Manual trigger for ad hoc/DRAFT orders once an admin believes the
    order is ready. Re-validates server-side via readiness_service — never
    trusts a client-side "looks ready" state."""
    from app.services import readiness_service

    result = readiness_service.check(order)
    if not result.ready:
        raise ReadinessNotMetError(result.missing)
    return transition(
        db, order, OrderStatus.READY_FOR_APPROVAL,
        actor_id=actor_id,
        actor_type=ActorType.SYSTEM if actor_id is None else ActorType.USER,
        audit_service=audit_service,
    )


def approve(
    db: Session, order: BirthdayOrder, *, actor_id: int | None,
    audit_service: AuditService | None = None,
) -> BirthdayOrder:
    """The one true approval gate (plan §2/§3): re-validates readiness
    server-side even though the order is already READY_FOR_APPROVAL,
    since state may have drifted (e.g. supplier unassigned) between the
    auto-promotion and this call."""
    from app.services import readiness_service

    result = readiness_service.check(order)
    if not result.ready:
        raise ReadinessNotMetError(result.missing)
    return transition(
        db, order, OrderStatus.APPROVED,
        actor_id=actor_id, actor_type=ActorType.USER, audit_service=audit_service,
    )


def reject(
    db: Session, order: BirthdayOrder, *, actor_id: int | None, reason: str,
    audit_service: AuditService | None = None,
) -> BirthdayOrder:
    return transition(
        db, order, OrderStatus.REJECTED,
        actor_id=actor_id, actor_type=ActorType.USER, detail=reason, audit_service=audit_service,
    )


class ReadinessNotMetError(Exception):
    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__(f"Order is not ready: missing {', '.join(missing)}")
