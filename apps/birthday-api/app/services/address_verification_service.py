"""P&C-manual address-verification workflow for cake delivery. No
automatic employee contact of any kind — a human (P&C/BIRTHDAY_ADMIN) sets
this status in the UI after doing their own outreach, and every change is
audited. Mirrors ``order_status_service.py``'s transition-then-audit shape
but deliberately has no transition table: a P&C user may move between any
two statuses at will (e.g. VERIFIED -> NEEDS_UPDATE after a bounced
delivery), unlike the supplier-fulfilment status machine's stricter rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.constants import (
    ActorType,
    AddressVerificationStatus,
    ExceptionReason,
    LeadTimeClass,
    OrderStatus,
)
from app.models.birthday_order import BirthdayOrder
from app.models.order_event import OrderEvent
from app.services import order_email_service, order_status_service, readiness_service
from app.services.audit_service import AuditService


def set_address_verification_status(
    db: Session,
    order: BirthdayOrder,
    new_status: AddressVerificationStatus,
    *,
    actor_id: int | None,
    note: str | None = None,
    audit_service: AuditService | None = None,
) -> BirthdayOrder:
    previous_status = order.address_verification_status
    order.address_verification_status = new_status.value

    # Reuses the order's existing OrderEvent timeline (same table the
    # STATUS_CHANGE/EMAIL_SENT/EMAIL_FAILED events already live in) so the
    # order-detail UI shows one unified history rather than a second,
    # separate log — the OrderEvent record IS the "workflow ref" the audit
    # entry ties back to.
    db.add(
        OrderEvent(
            order_id=order.id,
            event_type="ADDRESS_VERIFICATION_CHANGE",
            from_status=previous_status,
            to_status=new_status.value,
            actor_id=actor_id,
            actor_type="USER",
            detail=note,
        )
    )
    db.commit()
    db.refresh(order)

    service = audit_service or AuditService()
    try:
        # No address content is ever included here — only the status
        # values and an optional free-text note (which P&C is responsible
        # for not putting an address into; nothing in this service copies
        # order/employee address fields into the log by construction,
        # since BirthdayOrder itself does not store a street address).
        service.log(
            actor_id=actor_id,
            action="birthday.order.address_verification_change",
            entity_type="birthday_order",
            entity_id=order.id,
            previous_state={"address_verification_status": previous_status},
            new_state={"address_verification_status": new_status.value},
            metadata={"note": note} if note else None,
        )
    except Exception:  # noqa: BLE001 - best-effort, never fails the update
        pass

    return order


_ADDRESS_FIELDS = (
    "delivery_address_line1",
    "delivery_address_line2",
    "delivery_city",
    "delivery_state_province",
    "delivery_postal_code",
    "delivery_country",
)


def update_delivery_address(
    db: Session,
    order: BirthdayOrder,
    fields: dict[str, str | None],
    *,
    actor_id: int | None,
    audit_service: AuditService | None = None,
) -> BirthdayOrder:
    """P&C-manual correction of the delivery-address snapshot (plan §3D).
    Only ever called by a human — never by detection/automation. Marks the
    snapshot as ``MANUAL_CORRECTION`` so the UI can distinguish an edited
    address from the raw BambooHR value. The audit log records only which
    field NAMES changed, never the address content itself (same privacy
    precedent as the status-change log above)."""
    changed_fields = [
        name for name in _ADDRESS_FIELDS if name in fields and getattr(order, name) != fields[name]
    ]
    for name in changed_fields:
        setattr(order, name, fields[name])
    if changed_fields:
        order.delivery_address_source = "MANUAL_CORRECTION"

    db.commit()
    db.refresh(order)

    if changed_fields:
        service = audit_service or AuditService()
        try:
            # No address values in the audit trail — field names only.
            service.log(
                actor_id=actor_id,
                action="birthday.order.address_corrected",
                entity_type="birthday_order",
                entity_id=order.id,
                previous_state=None,
                new_state=None,
                metadata={"fields_changed": changed_fields},
            )
        except Exception:  # noqa: BLE001 - best-effort, never fails the update
            pass

    return order


@dataclass
class VerifyOutcome:
    order: BirthdayOrder
    auto_released: bool
    flagged_reasons: list[str] = field(default_factory=list)


def _classify_flags(order: BirthdayOrder, *, corrected: bool, config) -> list[str]:
    """Which exception triggers does this order carry right now (plan §K)?
    Any one of these routes a verified order to REQUIRES_REVIEW instead of
    auto-releasing it. Thresholds live on config so the business can widen
    or narrow the auto-release envelope without a deploy."""
    reasons: list[str] = []
    if corrected or order.delivery_address_source == "MANUAL_CORRECTION":
        reasons.append(ExceptionReason.ADDRESS_MANUALLY_CORRECTED.value)
    if order.lead_time_class in (LeadTimeClass.SHORT_NOTICE.value, LeadTimeClass.URGENT.value):
        reasons.append(ExceptionReason.SHORT_NOTICE_LEAD_TIME.value)
    if order.quantity != config.default_quantity:
        reasons.append(ExceptionReason.QUANTITY_CHANGED.value)
    return reasons


def verify_and_release(
    db: Session,
    order: BirthdayOrder,
    *,
    actor_id: int,
    corrected: bool = False,
    note: str | None = None,
    config,
    audit_service: AuditService | None = None,
) -> VerifyOutcome:
    """The one routine human checkpoint (plan §J/§K/§F). Marks the address
    VERIFIED, then immediately decides what happens next:

    - readiness still not met (no supplier / no delivery date / etc.) ->
      REQUIRES_ATTENTION, typed.
    - readiness met but the order carries an exception trigger, or the
      global auto-release switch is off -> REQUIRES_REVIEW, one click away
      from release.
    - readiness met and nothing flags it -> auto-released to the supplier
      immediately, system-actor, no further human action.
    """
    order = set_address_verification_status(
        db, order, AddressVerificationStatus.VERIFIED, actor_id=actor_id, note=note,
        audit_service=audit_service,
    )

    readiness = readiness_service.check(order)
    if not readiness.ready:
        order.exception_reason = ExceptionReason.NO_SUPPLIER.value if "supplier_not_assigned" in readiness.missing else None
        order = order_status_service.transition(
            db, order, OrderStatus.REQUIRES_ATTENTION,
            actor_id=actor_id, actor_type=ActorType.USER,
            detail=f"Verified, but not ready to release: {', '.join(readiness.missing)}",
        )
        return VerifyOutcome(order=order, auto_released=False, flagged_reasons=readiness.missing)

    flags = _classify_flags(order, corrected=corrected, config=config)
    if flags or not config.auto_release_enabled:
        order.exception_reason = flags[0] if flags else None
        order = order_status_service.transition(
            db, order, OrderStatus.REQUIRES_REVIEW,
            actor_id=actor_id, actor_type=ActorType.USER,
            detail=f"Flagged for one-click review: {', '.join(flags) or 'auto-release paused'}",
        )
        return VerifyOutcome(order=order, auto_released=False, flagged_reasons=flags)

    order.exception_reason = None
    try:
        order = order_email_service.auto_release_order(db, order)
        return VerifyOutcome(order=order, auto_released=True, flagged_reasons=[])
    except order_email_service.NoSupplierAssignedError:
        order.exception_reason = ExceptionReason.NO_SUPPLIER.value
        order = order_status_service.transition(
            db, order, OrderStatus.REQUIRES_ATTENTION,
            actor_id=actor_id, actor_type=ActorType.USER, detail="Verified, but no supplier assigned",
        )
        return VerifyOutcome(order=order, auto_released=False, flagged_reasons=["no_supplier"])


def confirm_release(db: Session, order: BirthdayOrder, *, actor_id: int) -> BirthdayOrder:
    """One-click "Confirm & release" for a REQUIRES_REVIEW order — the
    exception-only approval (plan §K)."""
    return order_email_service.confirm_release_order(db, order, actor_id=actor_id)
