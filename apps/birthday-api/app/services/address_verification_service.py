"""P&C-manual address-verification workflow for cake delivery. No
automatic employee contact of any kind — a human (P&C/BIRTHDAY_ADMIN) sets
this status in the UI after doing their own outreach, and every change is
audited. Mirrors ``order_status_service.py``'s transition-then-audit shape
but deliberately has no transition table: a P&C user may move between any
two statuses at will (e.g. VERIFIED -> NEEDS_UPDATE after a bounced
delivery), unlike the supplier-fulfilment status machine's stricter rules.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.constants import AddressVerificationStatus
from app.models.birthday_order import BirthdayOrder
from app.models.order_event import OrderEvent
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
