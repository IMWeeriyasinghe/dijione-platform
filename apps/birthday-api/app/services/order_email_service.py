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

from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
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


class NotReleasableError(Exception):
    """Raised when an order's current status is not one release/send may
    be called from (plan §K: "verification is the approval" — there is no
    separate approval gate any more, only a status-reachability check)."""


# Statuses from which an order may become SENT_TO_SUPPLIER. Reachable via
# auto-release (standard, from PENDING_VERIFICATION), one-click confirm
# (flagged, from REQUIRES_REVIEW), or a manual resend after an exception.
_SENDABLE_STATUSES = {
    OrderStatus.PENDING_VERIFICATION, OrderStatus.REQUIRES_REVIEW, OrderStatus.REQUIRES_ATTENTION,
}


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


_RETRY_BASE_MINUTES = 5
_RETRY_CAP_MINUTES = 240


def _backoff_minutes(attempt: int) -> int:
    """Exponential backoff: 5, 10, 20, 40 … capped at 240 minutes."""
    return min(_RETRY_BASE_MINUTES * (2 ** max(attempt, 0)), _RETRY_CAP_MINUTES)


def _release_subject(order: BirthdayOrder) -> str:
    return f"[{order.order_reference}] Birthday Cake Order — {order.employee_name}"


def _has_successful_release(db: Session, order: BirthdayOrder) -> bool:
    """A SENT outbound EMAIL for this order carrying the order-release
    subject — used to guard against sending the release twice."""
    stmt = select(SupplierCommunication.id).where(
        SupplierCommunication.order_id == order.id,
        SupplierCommunication.channel == CommunicationChannel.EMAIL.value,
        SupplierCommunication.direction == CommunicationDirection.OUTBOUND.value,
        SupplierCommunication.status == CommunicationStatus.SENT.value,
        SupplierCommunication.subject == _release_subject(order),
    )
    return db.execute(stmt).first() is not None


def _record_communication(
    db: Session, order: BirthdayOrder, *, subject: str, body: str, status: str,
    message_id: str | None, last_error: str | None, retry_count: int,
    next_retry_at: datetime | None = None,
) -> SupplierCommunication:
    communication = SupplierCommunication(
        order_id=order.id,
        supplier_id=order.supplier_id,
        direction=CommunicationDirection.OUTBOUND.value,
        channel=CommunicationChannel.EMAIL.value,
        author_type=ActorType.SYSTEM.value,
        subject=subject,
        body=body,
        sent_at=datetime.now(UTC) if status == CommunicationStatus.SENT.value else None,
        message_id=message_id,
        status=status,
        retry_count=retry_count,
        next_retry_at=next_retry_at,
        last_error=last_error,
    )
    db.add(communication)
    db.flush()
    return communication


def _handle_failure(
    db: Session, order: BirthdayOrder, *, error_detail: str, actor_id: int | None,
    notify: bool = True,
) -> BirthdayOrder:
    """Records the failure and moves the order into the admin exception
    queue. ``notify=False`` while automatic retries remain — the
    BIRTHDAY_ADMIN notification is deferred until the retry sweep exhausts
    ``max_attempts`` (Phase 1 §1.3)."""
    order.last_failure_reason = error_detail
    order.retry_count = (order.retry_count or 0) + 1

    from_status = OrderStatus(order.status)
    if from_status != OrderStatus.REQUIRES_ATTENTION:
        order = order_status_service.transition(
            db, order, OrderStatus.REQUIRES_ATTENTION,
            actor_id=actor_id, actor_type=ActorType.SYSTEM, detail=error_detail,
        )

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

    if notify:
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
    released_by: int | None = None, guard_duplicate: bool = False,
    actor_display_name: str | None = None,
) -> BirthdayOrder:
    if order.supplier is None:
        raise NoSupplierAssignedError(f"Order {order.order_reference} has no supplier assigned")
    # Duplicate-send guard (Phase 1 §1.3): a release path (auto-release,
    # manual send, confirm-release) is a no-op if the release email already
    # went out for this order. An explicit resend / the retry sweep pass
    # guard_duplicate=False.
    if guard_duplicate and _has_successful_release(db, order):
        return order
    # "Verification is the approval" (decision A): there is no separate
    # approval gate. The only status check is reachability — a standard
    # order auto-releases from PENDING_VERIFICATION, a flagged order
    # releases from REQUIRES_REVIEW via one-click confirm, and a prior
    # failure may retry from REQUIRES_ATTENTION.
    if OrderStatus(order.status) not in _SENDABLE_STATUSES:
        raise NotReleasableError(
            f"Order {order.order_reference} is not in a sendable state "
            f"(current status: {order.status})"
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

    # First automatic retry is scheduled ~5 min out; the sweep escalates.
    _first_retry_at = datetime.now(UTC) + timedelta(minutes=_backoff_minutes(0))

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
            next_retry_at=_first_retry_at,
        )
        return _handle_failure(db, order, error_detail=str(exc), actor_id=actor_id, notify=False)

    if not result.sent:
        error_detail = "Email send reported failure (sent=False)"
        _record_communication(
            db, order, subject=subject, body=body, status=CommunicationStatus.FAILED.value,
            message_id=result.message_id, last_error=error_detail, retry_count=retry_count,
            next_retry_at=_first_retry_at,
        )
        return _handle_failure(db, order, error_detail=error_detail, actor_id=actor_id, notify=False)

    _record_communication(
        db, order, subject=subject, body=body, status=CommunicationStatus.SENT.value,
        message_id=result.message_id, last_error=None, retry_count=retry_count,
    )
    order.released_at = datetime.now(UTC)
    order.released_by = released_by
    order = order_status_service.transition(
        db, order, target_status,
        actor_id=actor_id, actor_type=ActorType.SYSTEM if actor_id is None else ActorType.USER,
        detail=f"Email sent, message_id={result.message_id}",
        event_type="AUTO_RELEASED" if released_by is None else "STATUS_CHANGE",
        actor_display_name=actor_display_name if actor_id is not None else "System",
    )
    db.add(
        OrderEvent(
            order_id=order.id,
            event_type="EMAIL_SENT",
            from_status=None,
            to_status=order.status,
            actor_id=actor_id,
            actor_type=ActorType.SYSTEM.value if actor_id is None else ActorType.USER.value,
            actor_display_name=actor_display_name if actor_id is not None else "System",
            detail=f"message_id={result.message_id}",
        )
    )
    db.commit()
    db.refresh(order)
    return order


def send_order_to_supplier(
    db: Session, order: BirthdayOrder, *, actor_id: int | None, actor_display_name: str | None = None,
) -> BirthdayOrder:
    """Manual release — used for held orders and one-off ad hoc sends.
    Recorded as human-released (released_by=actor_id)."""
    return _send(
        db, order, actor_id=actor_id, target_status=OrderStatus.SENT_TO_SUPPLIER,
        released_by=actor_id, guard_duplicate=True, actor_display_name=actor_display_name,
    )


def auto_release_order(db: Session, order: BirthdayOrder) -> BirthdayOrder:
    """The standard-order path (plan §F step 10): triggered by
    address_verification_service the instant a standard order is marked
    VERIFIED. released_by stays NULL — this is a SYSTEM action."""
    return _send(
        db, order, actor_id=None, target_status=OrderStatus.SENT_TO_SUPPLIER,
        released_by=None, guard_duplicate=True,
    )


def confirm_release_order(
    db: Session, order: BirthdayOrder, *, actor_id: int, actor_display_name: str | None = None,
) -> BirthdayOrder:
    """The one-click "Confirm & release" action for a flagged
    (REQUIRES_REVIEW) order — the exception-only approval (plan §K)."""
    order.review_confirmed_at = datetime.now(UTC)
    order.review_confirmed_by = actor_id
    return _send(
        db, order, actor_id=actor_id, target_status=OrderStatus.SENT_TO_SUPPLIER,
        released_by=actor_id, guard_duplicate=True, actor_display_name=actor_display_name,
    )


def resend_order_to_supplier(
    db: Session, order: BirthdayOrder, *, actor_id: int | None, actor_display_name: str | None = None,
) -> BirthdayOrder:
    """Manual retry for orders already SENT_TO_SUPPLIER/REQUIRES_ATTENTION
    after a prior failure — same order_reference, never a second order.
    Explicit, so the duplicate guard does not apply."""
    return _send(
        db, order, actor_id=actor_id, target_status=OrderStatus.SENT_TO_SUPPLIER,
        released_by=actor_id, actor_display_name=actor_display_name,
    )


def retry_failed_outbound(db: Session, *, now: datetime | None = None) -> dict:
    """Automatic backoff retry for FAILED outbound emails (Phase 1 §1.3),
    driven by ``birthday-comms-job``. Re-sends each due row; on success the
    row flips to SENT and, if the order is parked in REQUIRES_ATTENTION for
    this send, it advances to SENT_TO_SUPPLIER. When ``max_attempts`` is
    exhausted the BIRTHDAY_ADMIN notification finally fires and the order
    stays in the exception queue for a human."""
    now = now or datetime.now(UTC)
    rows = db.execute(
        select(SupplierCommunication).where(
            SupplierCommunication.channel == CommunicationChannel.EMAIL.value,
            SupplierCommunication.direction == CommunicationDirection.OUTBOUND.value,
            SupplierCommunication.status == CommunicationStatus.FAILED.value,
            SupplierCommunication.retry_count < SupplierCommunication.max_attempts,
            or_(
                SupplierCommunication.next_retry_at.is_(None),
                SupplierCommunication.next_retry_at <= now,
            ),
        )
    ).scalars().all()

    retried = succeeded = exhausted = 0
    for comm in rows:
        order = db.get(BirthdayOrder, comm.order_id)
        if order is None:
            comm.next_retry_at = None
            comm.retry_count = comm.max_attempts
            continue
        if order.supplier is None or not order.supplier.primary_contact_email:
            # Nothing to retry against — treat as exhausted so a human is told.
            comm.next_retry_at = None
            comm.retry_count = comm.max_attempts
            comm.last_error = "No supplier contact email"
            exhausted += 1
            db.add(
                OrderEvent(
                    order_id=order.id, event_type="EMAIL_RETRY_EXHAUSTED",
                    actor_type=ActorType.SYSTEM.value,
                    detail="No supplier contact email — cannot send",
                )
            )
            try:
                NotificationService().notify_module_role(
                    module_key="birthday", role="BIRTHDAY_ADMIN",
                    type="birthday.email_failed",
                    title=f"Supplier email cannot be sent for {order.order_reference}",
                    body="The assigned supplier has no contact email.",
                    related_entity_type="birthday_order", related_entity_id=order.id,
                )
            except Exception:  # noqa: BLE001
                pass
            continue
        retried += 1
        try:
            result = get_email_client().send(
                to=order.supplier.primary_contact_email, subject=comm.subject,
                body=comm.body, order_reference=order.order_reference,
            )
            ok = bool(result.sent)
            err = None if ok else "sent=False"
            msg_id = result.message_id
        except Exception as exc:  # noqa: BLE001
            ok, err, msg_id = False, str(exc), None

        comm.retry_count += 1
        if ok:
            comm.status = CommunicationStatus.SENT.value
            comm.sent_at = now
            comm.next_retry_at = None
            comm.last_error = None
            comm.message_id = msg_id or comm.message_id
            succeeded += 1
            if order.status == OrderStatus.REQUIRES_ATTENTION.value:
                try:
                    order = order_status_service.transition(
                        db, order, OrderStatus.SENT_TO_SUPPLIER,
                        actor_id=None, actor_type=ActorType.SYSTEM,
                        detail="Supplier email delivered on automatic retry",
                    )
                    order.released_at = order.released_at or now
                except order_status_service.InvalidTransitionError:
                    pass
            db.add(
                OrderEvent(
                    order_id=order.id, event_type="EMAIL_SENT", to_status=order.status,
                    actor_type=ActorType.SYSTEM.value,
                    detail=f"retry #{comm.retry_count} succeeded",
                )
            )
        else:
            comm.last_error = err
            if comm.retry_count >= comm.max_attempts:
                comm.next_retry_at = None
                exhausted += 1
                db.add(
                    OrderEvent(
                        order_id=order.id, event_type="EMAIL_RETRY_EXHAUSTED",
                        actor_type=ActorType.SYSTEM.value,
                        detail=f"{comm.retry_count} attempts failed: {err}",
                    )
                )
                try:
                    NotificationService().notify_module_role(
                        module_key="birthday", role="BIRTHDAY_ADMIN",
                        type="birthday.email_failed",
                        title=f"Supplier email failed for {order.order_reference} after {comm.retry_count} attempts",
                        body=err or "unknown error",
                        related_entity_type="birthday_order", related_entity_id=order.id,
                    )
                except Exception:  # noqa: BLE001
                    pass
            else:
                comm.next_retry_at = now + timedelta(minutes=_backoff_minutes(comm.retry_count))

    db.commit()
    return {"due": len(rows), "retried": retried, "succeeded": succeeded, "exhausted": exhausted}


def send_ad_hoc_message(
    db: Session, order: BirthdayOrder, *, body: str, actor_id: int | None
) -> SupplierCommunication:
    """Flow 2/3 (§G): an internal-authored email to the supplier that is not
    an order-release — a message nudge, a change note, etc. Records a
    ``SupplierCommunication(channel=EMAIL, direction=OUTBOUND)`` and never
    changes order status. Best-effort: a send failure is recorded on the
    row (picked up by the retry sweep) but does not raise."""
    if order.supplier is None or not order.supplier.primary_contact_email:
        return _record_communication(
            db, order, subject="", body=body, status=CommunicationStatus.FAILED.value,
            message_id=None, last_error="No supplier contact email", retry_count=0,
        )
    subject = f"[{order.order_reference}] Update — {order.employee_name}"
    full_body = (
        f"Order Reference: {order.order_reference}\n\n{body}\n\n"
        f"Open the DijiBirthday Supplier Portal to view and respond to this order."
    )
    try:
        result = get_email_client().send(
            to=order.supplier.primary_contact_email, subject=subject, body=full_body,
            order_reference=order.order_reference,
        )
    except Exception as exc:  # noqa: BLE001
        return _record_communication(
            db, order, subject=subject, body=full_body, status=CommunicationStatus.FAILED.value,
            message_id=None, last_error=str(exc), retry_count=0,
        )
    comm = _record_communication(
        db, order, subject=subject, body=full_body,
        status=CommunicationStatus.SENT.value if result.sent else CommunicationStatus.FAILED.value,
        message_id=result.message_id, last_error=None if result.sent else "sent=False", retry_count=0,
    )
    comm.author_type = ActorType.USER.value if actor_id is not None else ActorType.SYSTEM.value
    comm.author_id = actor_id
    db.commit()
    return comm
