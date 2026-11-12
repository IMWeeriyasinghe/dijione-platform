"""Internal "Unmatched supplier email" queue (Phase 1 §H.3). An authorized
user links a quarantined email to an order — promoting it to a real INBOUND
``SupplierCommunication`` — or dismisses it. Linking never mutates order
state; the user may optionally also raise a structured issue."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import BirthdayScope, require_birthday_permission
from app.core.constants import (
    ActorType,
    CommunicationChannel,
    CommunicationDirection,
    CommunicationStatus,
    OrderIssueStatus,
)
from app.db.session import get_db
from app.models.birthday_order import BirthdayOrder
from app.models.inbound_email import InboundEmail
from app.models.order_event import OrderEvent
from app.models.order_issue import OrderIssue
from app.models.supplier_communication import SupplierCommunication
from app.services.audit_service import AuditService

router = APIRouter(prefix="/api/birthday/inbound-emails", tags=["birthday-inbound-email"])


class InboundEmailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_address: str
    subject: str
    body_preview: str
    received_at: datetime | None
    attachment_count: int
    status: str
    reason: str
    linked_order_id: int | None
    created_at: datetime


class LinkRequest(BaseModel):
    # Accept either the numeric order id or the human order reference
    # (BDAY-EMP…/BDAY-TMP…) — an operator only knows the reference (§H4).
    order_id: int | None = None
    order_reference: str | None = None
    raise_issue: bool = False
    issue_type: str = "OTHER"


@router.get("", response_model=list[InboundEmailOut])
def list_unmatched_emails(
    include_resolved: bool = False,
    db: Session = Depends(get_db),
    _scope: BirthdayScope = Depends(require_birthday_permission("birthday.orders.read")),
) -> list[InboundEmail]:
    stmt = select(InboundEmail).order_by(InboundEmail.created_at.desc())
    if not include_resolved:
        stmt = stmt.where(InboundEmail.status == "UNMATCHED")
    return list(db.execute(stmt.limit(200)).scalars().all())


def _get_or_404(db: Session, inbound_id: int) -> InboundEmail:
    row = db.get(InboundEmail, inbound_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Inbound email not found")
    return row


@router.post("/{inbound_id}/link", response_model=InboundEmailOut)
def link_unmatched_email(
    inbound_id: int,
    payload: LinkRequest,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.orders.update")),
) -> InboundEmail:
    row = _get_or_404(db, inbound_id)
    if row.status != "UNMATCHED":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Already {row.status.lower()}")
    order: BirthdayOrder | None = None
    if payload.order_id is not None:
        order = db.get(BirthdayOrder, payload.order_id)
    elif payload.order_reference:
        ref = payload.order_reference.strip()
        order = db.execute(
            select(BirthdayOrder).where(BirthdayOrder.order_reference == ref)
        ).scalars().first()
        # tolerate a bare numeric string too
        if order is None and ref.isdigit():
            order = db.get(BirthdayOrder, int(ref))
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "order_id or order_reference required")
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")

    issue_id = None
    if payload.raise_issue:
        issue = OrderIssue(
            order_id=order.id, raised_by_type="USER", raised_by_id=scope.user.id,
            type=payload.issue_type, detail=row.body_preview[:2000],
            status=OrderIssueStatus.OPEN.value,
        )
        db.add(issue)
        db.flush()
        issue_id = issue.id

    db.add(
        SupplierCommunication(
            order_id=order.id, supplier_id=order.supplier_id,
            direction=CommunicationDirection.INBOUND.value,
            channel=CommunicationChannel.EMAIL.value,
            author_type=ActorType.SUPPLIER.value,
            subject=row.subject, body=row.body_preview,
            received_at=row.received_at or datetime.now(UTC),
            message_id=row.provider_message_id,
            status=CommunicationStatus.REPLIED.value,
            issue_id=issue_id,
        )
    )
    db.add(
        OrderEvent(
            order_id=order.id, event_type="SUPPLIER_EMAIL_REPLY",
            actor_id=scope.user.id, actor_type=ActorType.USER.value,
            actor_display_name=scope.user.full_name,
            detail=f"Manually linked from the unmatched queue: {row.body_preview[:240]}",
        )
    )
    row.status = "LINKED"
    row.linked_order_id = order.id
    row.linked_by = scope.user.id
    row.resolved_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
    try:
        AuditService().log(
            actor_id=scope.user.id, action="birthday.inbound_email.link",
            entity_type="birthday_order", entity_id=order.id,
            metadata={"inbound_email_id": row.id, "raised_issue": bool(issue_id)},
        )
    except Exception:  # noqa: BLE001
        pass
    return row


@router.post("/{inbound_id}/dismiss", response_model=InboundEmailOut)
def dismiss_unmatched_email(
    inbound_id: int,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.orders.update")),
) -> InboundEmail:
    row = _get_or_404(db, inbound_id)
    if row.status != "UNMATCHED":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Already {row.status.lower()}")
    row.status = "DISMISSED"
    row.linked_by = scope.user.id
    row.resolved_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
    return row
