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
