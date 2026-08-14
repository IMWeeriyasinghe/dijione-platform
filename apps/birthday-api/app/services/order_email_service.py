"""Phase D — renders and sends the supplier-instruction email for an order,
and records the outcome. Never lets an exception propagate silently: every
failure is caught, recorded as a ``SupplierCommunication``/``OrderEvent``,
and surfaced to ``BIRTHDAY_ADMIN`` (plan §9, §11).

Retry/resend row design: each send/resend attempt writes a **new**
``SupplierCommunication`` row (rather than mutating/incrementing a single
row) — this keeps the communications timeline an honest, append-only
history of every attempt (what was actually sent when, and what the result
was), which is what the order-detail UI's timeline is meant to show, and
matches ``SupplierCommunication.retry_count`` reading naturally as "which
attempt number is this" per row.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.constants import (
    ActorType,
    AddressVerificationStatus,
    CommunicationChannel,
    CommunicationDirection,
    CommunicationStatus,
    OrderStatus,
    SpecialRequirementKind,
)
from app.integrations.factory import get_email_client
from app.models.birthday_order import BirthdayOrder
from app.models.order_event import OrderEvent
from app.models.supplier_communication import SupplierCommunication
from app.services import order_status_service
from app.services.notification_service import NotificationService


class NoSupplierAssignedError(Exception):
    """Raised when an order has no resolved supplier to send to."""


class AddressNotVerifiedError(Exception):
    """Raised when an order is sent/resent to a supplier before P&C has
    verified the delivery address (plan cake-order gate requirement #10) —
    the order remains visible as "needs P&C action", never silently
    dropped; it just cannot progress to SENT_TO_SUPPLIER yet."""


class ApprovalRequiredError(Exception):
    """Raised when an order has not been through the explicit approval
    workflow (Phase-Next §2/§3) — only APPROVED orders (or
    REQUIRES_ATTENTION orders retrying a previously-approved send) may
    become supplier-visible/actionable."""


def render_supplier_email(order: BirthdayOrder) -> tuple[str, str]:
    """Renders (subject, body). MUST include ``order_reference``, employee
    name, birthday date, delivery/office location, and quantity.

    Isolation (plan §11, critical): SUPPLIER_INSTRUCTION-kind special
    requirements are included; INTERNAL_NOTE-kind text is NEVER included in
    the rendered email, by construction — only requirements whose kind
    equals SUPPLIER_INSTRUCTION are read into the template at all.
    """
    subject = f"[{order.order_reference}] Birthday Cake Order — {order.employee_name}"

    lines = [
        f"Order Reference: {order.order_reference}",
        f"Employee: {order.employee_name}",
        f"Birthday Date: {order.birthday_date.isoformat()}",
        f"Delivery / Office Location: {order.office_location}",
        f"Quantity: {order.quantity}",
    ]

    supplier_instructions = [
        req.text
        for req in (order.special_requirements or [])
        if req.kind == SpecialRequirementKind.SUPPLIER_INSTRUCTION.value
    ]
    if supplier_instructions:
        lines.append("")
        lines.append("Special Instructions:")
        lines.extend(f"- {text}" for text in supplier_instructions)

    lines.append("")
    lines.append(f"Please confirm receipt of order {order.order_reference}.")

    body = "\n".join(lines)
    return subject, body


def _record_communication(
    db: Session, order: BirthdayOrder, *, subject: str, body: str, status: str,
    message_id: str | None, last_error: str | None, retry_count: int,
) -> SupplierCommunication:
    communication = SupplierCommunication(
        order_id=order.id,
        supplier_id=order.supplier_id,
        direction=CommunicationDirection.OUTBOUND.value,
        channel=CommunicationChannel.EMAIL.value,
        subject=subject,
        body=body,
        sent_at=datetime.now(UTC) if status == CommunicationStatus.SENT.value else None,
        message_id=message_id,
        status=status,
        retry_count=retry_count,
        last_error=last_error,
    )
    db.add(communication)
    db.flush()
    return communication


def _handle_failure(
    db: Session, order: BirthdayOrder, *, error_detail: str, actor_id: int | None,
) -> BirthdayOrder:
    """Records the failure and moves the order into the admin exception
    queue. Never lets the failure disappear silently."""
    order.last_failure_reason = error_detail
    order.retry_count = (order.retry_count or 0) + 1

    from_status = OrderStatus(order.status)
    if from_status != OrderStatus.REQUIRES_ATTENTION:
        order = order_status_service.transition(
            db, order, OrderStatus.REQUIRES_ATTENTION,
            actor_id=actor_id, actor_type=ActorType.SYSTEM, detail=error_detail,
        )

    # transition() (when it ran) already wrote a STATUS_CHANGE OrderEvent;
    # the EMAIL_FAILED event is added separately so the failure reason is
    # distinguishable from a generic status change in the timeline, and is
    # still recorded even on a repeat failure that doesn't change status.
    db.add(
        OrderEvent(
            order_id=order.id,
            event_type="EMAIL_FAILED",
            from_status=from_status.value,
            to_status=OrderStatus.REQUIRES_ATTENTION.value,
            actor_id=actor_id,
            actor_type=ActorType.SYSTEM.value,
            detail=error_detail,
        )
    )
    db.commit()
    db.refresh(order)

    try:
        NotificationService().notify_module_role(
            module_key="birthday",
            role="BIRTHDAY_ADMIN",
            type="birthday.email_failed",
            title=f"Supplier email failed for {order.order_reference}",
            body=error_detail,
            related_entity_type="birthday_order",
            related_entity_id=order.id,
        )
    except Exception:  # noqa: BLE001 - best-effort, never fails the flow
        pass

    return order


def _send(
    db: Session, order: BirthdayOrder, *, actor_id: int | None, target_status: OrderStatus,
) -> BirthdayOrder:
    if order.supplier is None:
        raise NoSupplierAssignedError(f"Order {order.order_reference} has no supplier assigned")
    # Approval gate (Phase-Next §2/§3): only an APPROVED order may become
    # supplier-visible for the first time; REQUIRES_ATTENTION is allowed so
    # a previously-approved send that failed can be retried without
    # re-running the approval step.
    if order.status not in (OrderStatus.APPROVED.value, OrderStatus.REQUIRES_ATTENTION.value):
        raise ApprovalRequiredError(
            f"Order {order.order_reference} must be APPROVED before it can be sent to "
            f"the supplier (current status: {order.status})"
        )
    # Cake-order gate (plan requirement #10): eligibility was already
    # enforced at order-creation time (an ineligible employee never gets a
    # BirthdayOrder row — see detection_service.run_daily_scan), so the one
    # remaining gate to check at send-time is address verification. Address
    # is a P&C-manual, per-order-lifecycle fact (can change between orders
    # for the same employee) so it cannot be pre-checked at creation time.
    if order.address_verification_status != AddressVerificationStatus.VERIFIED.value:
        raise AddressNotVerifiedError(
            f"Order {order.order_reference} cannot be sent to the supplier until P&C "
            f"verifies the delivery address (current status: "
            f"{order.address_verification_status})"
        )

    subject, body = render_supplier_email(order)
    retry_count = (order.retry_count or 0) + 1 if order.status == OrderStatus.REQUIRES_ATTENTION.value else 0

    try:
        result = get_email_client().send(
            to=order.supplier.primary_contact_email,
            subject=subject,
            body=body,
            order_reference=order.order_reference,
        )
    except Exception as exc:  # noqa: BLE001 - integration failures must never propagate silently
        _record_communication(
            db, order, subject=subject, body=body, status=CommunicationStatus.FAILED.value,
            message_id=None, last_error=str(exc), retry_count=retry_count,
        )
        return _handle_failure(db, order, error_detail=str(exc), actor_id=actor_id)

    if not result.sent:
        error_detail = "Email send reported failure (sent=False)"
        _record_communication(
            db, order, subject=subject, body=body, status=CommunicationStatus.FAILED.value,
            message_id=result.message_id, last_error=error_detail, retry_count=retry_count,
        )
        return _handle_failure(db, order, error_detail=error_detail, actor_id=actor_id)

    _record_communication(
        db, order, subject=subject, body=body, status=CommunicationStatus.SENT.value,
        message_id=result.message_id, last_error=None, retry_count=retry_count,
    )
    order = order_status_service.transition(
        db, order, target_status,
        actor_id=actor_id, actor_type=ActorType.SYSTEM if actor_id is None else ActorType.USER,
        detail=f"Email sent, message_id={result.message_id}",
    )
    db.add(
        OrderEvent(
            order_id=order.id,
            event_type="EMAIL_SENT",
            from_status=None,
            to_status=order.status,
            actor_id=actor_id,
            actor_type=ActorType.SYSTEM.value if actor_id is None else ActorType.USER.value,
            detail=f"message_id={result.message_id}",
        )
    )
    db.commit()
    db.refresh(order)
    return order


def send_order_to_supplier(db: Session, order: BirthdayOrder, *, actor_id: int | None) -> BirthdayOrder:
    return _send(db, order, actor_id=actor_id, target_status=OrderStatus.SENT_TO_SUPPLIER)


def resend_order_to_supplier(db: Session, order: BirthdayOrder, *, actor_id: int | None) -> BirthdayOrder:
    """Manual retry for orders already SENT_TO_SUPPLIER/REQUIRES_ATTENTION
    after a prior failure — same order_reference, never a second order."""
    target_status = OrderStatus.SENT_TO_SUPPLIER
    order = _send(db, order, actor_id=actor_id, target_status=target_status)
    return order
