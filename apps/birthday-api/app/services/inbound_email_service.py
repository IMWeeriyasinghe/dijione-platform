"""Inbound supplier email — flow 4 of §G (Phase 1 §1.5).

Polling only (§H.0): ``poll()`` reads the shared mailbox since a watermark
and ``ingest_message()`` correlates each message. A matched reply becomes a
single ``SupplierCommunication(channel=EMAIL, direction=INBOUND)`` plus an
internal notification — **and nothing else**. NO ``OrderIssue`` is
auto-created from free text: "Thanks, received." is normal communication.
An issue is created / linked only by a deliberate action (structured
"Report a problem", a manual link, or a reply threading onto an existing
issue). Uncorrelated / unsafe mail is quarantined in ``inbound_emails``.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import (
    ActorType,
    CommunicationChannel,
    CommunicationDirection,
    CommunicationStatus,
)
from app.integrations.factory import get_inbound_mail_client
from app.integrations.inbound_mail.client import InboundMessage
from app.models.birthday_order import BirthdayOrder
from app.models.inbound_email import InboundEmail, InboundPollState
from app.models.order_event import OrderEvent
from app.models.supplier import Supplier
from app.models.supplier_communication import SupplierCommunication
from app.models.supplier_user import SupplierUser
from app.services.communication_service import sanitise_message_body
from app.services.notification_service import NotificationService

_ORDER_REF_RE = re.compile(r"BDAY-(?:EMP|TMP)[A-Za-z0-9]+-\d{4}-\d{5}")


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite drops tzinfo; treat every stored timestamp as UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _extract_order_reference(*texts: str) -> str | None:
    for t in texts:
        m = _ORDER_REF_RE.search(t or "")
        if m:
            return m.group(0)
    return None


def _match_by_headers(db: Session, msg: InboundMessage) -> SupplierCommunication | None:
    ids = [i for i in (*msg.in_reply_to, *msg.references) if i]
    if not ids:
        return None
    return db.execute(
        select(SupplierCommunication).where(
            SupplierCommunication.channel == CommunicationChannel.EMAIL.value,
            SupplierCommunication.direction == CommunicationDirection.OUTBOUND.value,
            SupplierCommunication.message_id.in_(ids),
        )
    ).scalars().first()


def _sender_is_authorised(db: Session, order: BirthdayOrder, from_address: str) -> tuple[bool, int | None]:
    """The sender must be an ACTIVE SupplierUser of this order's supplier,
    or the supplier's primary contact address."""
    addr = (from_address or "").strip().lower()
    if not addr or order.supplier_id is None:
        return False, None
    su = db.execute(
        select(SupplierUser).where(
            SupplierUser.supplier_id == order.supplier_id,
            SupplierUser.status == "ACTIVE",
        )
    ).scalars().all()
    for u in su:
        if (u.email or "").strip().lower() == addr:
            return True, u.id
    supplier = db.get(Supplier, order.supplier_id)
    if supplier and (supplier.primary_contact_email or "").strip().lower() == addr:
        return True, None
    return False, None


def _already_ingested(db: Session, provider_message_id: str) -> bool:
    if db.execute(
        select(SupplierCommunication.id).where(SupplierCommunication.message_id == provider_message_id)
    ).first():
        return True
    if db.execute(
        select(InboundEmail.id).where(InboundEmail.provider_message_id == provider_message_id)
    ).first():
        return True
    return False


def _quarantine(db: Session, msg: InboundMessage, reason: str) -> str:
    row = InboundEmail(
        provider_message_id=msg.id,
        from_address=(msg.from_address or "")[:320],
        subject=(msg.subject or "")[:500],
        body_preview=sanitise_message_body(msg.body_text)[:2000],
        received_at=msg.received_at,
        attachment_count=msg.attachment_count,
        status="UNMATCHED",
        reason=reason[:255],
    )
    db.add(row)
    db.commit()
    try:
        NotificationService().notify_module_role(
            module_key="birthday", role="BIRTHDAY_ADMIN", type="birthday.unmatched_email",
            title="Unmatched supplier email",
            body=f"From {msg.from_address or '?'} — {reason}. Subject: {msg.subject or '(none)'}",
        )
    except Exception:  # noqa: BLE001
        pass
    return "quarantined"


def ingest_message(db: Session, msg: InboundMessage) -> str:
    """Correlate + persist one inbound message. Returns
    "matched" | "quarantined" | "duplicate". Never mutates order state."""
    if not msg.id:
        return "quarantined"
    if _already_ingested(db, msg.id):
        return "duplicate"

    matched_outbound = _match_by_headers(db, msg)
    order: BirthdayOrder | None = None
    if matched_outbound is not None:
        order = db.get(BirthdayOrder, matched_outbound.order_id)

    if order is None:
        ref = _extract_order_reference(msg.subject, msg.body_text)
        if ref:
            order = db.execute(
                select(BirthdayOrder).where(BirthdayOrder.order_reference == ref)
            ).scalars().first()

    if order is None:
        return _quarantine(db, msg, "no order reference or matching thread")

    authorised, supplier_user_id = _sender_is_authorised(db, order, msg.from_address)
    if not authorised:
        return _quarantine(
            db, msg,
            f"sender {msg.from_address or '?'} is not an active user of this order's supplier",
        )

    body = sanitise_message_body(msg.body_text)
    comm = SupplierCommunication(
        order_id=order.id,
        supplier_id=order.supplier_id,
        direction=CommunicationDirection.INBOUND.value,
        channel=CommunicationChannel.EMAIL.value,
        author_type=ActorType.SUPPLIER.value,
        author_id=supplier_user_id,
        subject=(msg.subject or "")[:500],
        body=body,
        received_at=msg.received_at or datetime.now(UTC),
        message_id=msg.id,
        in_reply_to=(msg.in_reply_to[0] if msg.in_reply_to else None),
        status=CommunicationStatus.REPLIED.value,
        # Inherit an existing thread's issue — never create a new one.
        issue_id=matched_outbound.issue_id if matched_outbound is not None else None,
    )
    db.add(comm)
    db.add(
        OrderEvent(
            order_id=order.id, event_type="SUPPLIER_EMAIL_REPLY",
            actor_id=supplier_user_id, actor_type=ActorType.SUPPLIER.value,
            detail=body[:280] + (f"  [{msg.attachment_count} attachment(s) withheld]" if msg.attachment_count else ""),
        )
    )
    db.commit()

    try:
        NotificationService().notify_module_role(
            module_key="birthday", role="BIRTHDAY_ADMIN", type="birthday.supplier_email_reply",
            title=f"Supplier email reply on {order.order_reference}",
            body=body[:280],
            related_entity_type="birthday_order", related_entity_id=order.id,
        )
    except Exception:  # noqa: BLE001
        pass
    return "matched"


def _poll_state(db: Session) -> InboundPollState:
    state = db.execute(select(InboundPollState).limit(1)).scalars().first()
    if state is None:
        state = InboundPollState(id=1, last_received_at=None)
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def poll(db: Session, *, now: datetime | None = None) -> dict:
    """Driven by ``birthday-comms-job`` (~10 min). Reads the mailbox since
    the watermark, ingests each message, and advances the watermark only on
    a fully successful pass."""
    now = now or datetime.now(UTC)
    state = _poll_state(db)
    watermark = _aware(state.last_received_at)
    client = get_inbound_mail_client()
    messages = client.list_messages_since(watermark, limit=50)

    counts = {"seen": len(messages), "matched": 0, "quarantined": 0, "duplicate": 0}
    max_received = watermark
    ok = True
    for msg in messages:
        rcv = _aware(msg.received_at)
        try:
            outcome = ingest_message(db, msg)
            counts[outcome] = counts.get(outcome, 0) + 1
            if rcv is not None and (max_received is None or rcv > max_received):
                max_received = rcv
        except Exception:  # noqa: BLE001 - one bad message must not stall the poll
            db.rollback()
            ok = False

    advanced = ok and max_received is not None and max_received != watermark
    if advanced:
        state.last_received_at = max_received
        db.commit()
    return {**counts, "watermark_advanced": advanced}
