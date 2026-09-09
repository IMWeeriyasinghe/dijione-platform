"""Communication subsystem (Phase 1 §G) — a first-class peer of the order
lifecycle. Two channels (Portal, Email), both fully bidirectional; every
message persists to the single ``SupplierCommunication`` store and renders
in one **Unified Timeline** per order, audience-filtered.

This module owns the Portal message flows (1 & 2) and the timeline merge.
Outbound email (flow 3) lives in ``order_email_service``; inbound email
(flow 4) in ``inbound_email_service``; both also write ``SupplierCommunication``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import (
    ActorType,
    CommunicationChannel,
    CommunicationDirection,
    CommunicationStatus,
    OrderIssueStatus,
)
from app.models.birthday_order import BirthdayOrder
from app.models.order_event import OrderEvent
from app.models.order_issue import OrderIssue
from app.models.supplier_communication import SupplierCommunication
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService

_MAX_MESSAGE_CHARS = 8000
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def sanitise_message_body(raw: str) -> str:
    """Strip any markup (including the *content* of <script>/<style>) and
    clamp length. Portal messages are plain text; inbound email HTML is
    reduced to text here."""
    text = _SCRIPT_STYLE_RE.sub(" ", raw or "")
    text = _TAG_RE.sub(" ", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    return text[:_MAX_MESSAGE_CHARS]


def post_portal_message(
    db: Session,
    order: BirthdayOrder,
    *,
    author_type: ActorType,
    author_id: int | None,
    body: str,
    issue_id: int | None = None,
) -> SupplierCommunication:
    """Flow 1 (supplier -> internal) and flow 2 (internal -> supplier):
    a message posted on an order in either portal. Direction is relative to
    the supplier."""
    clean = sanitise_message_body(body)
    if not clean:
        raise ValueError("Message body is empty")

    direction = (
        CommunicationDirection.OUTBOUND
        if author_type == ActorType.USER
        else CommunicationDirection.INBOUND
    )
    comm = SupplierCommunication(
        order_id=order.id,
        supplier_id=order.supplier_id,
        direction=direction.value,
        channel=CommunicationChannel.PORTAL.value,
        author_type=author_type.value,
        author_id=author_id,
        body=clean,
        status=CommunicationStatus.POSTED.value,
        issue_id=issue_id,
    )
    db.add(comm)
    db.add(
        OrderEvent(
            order_id=order.id,
            event_type="PORTAL_MESSAGE",
            actor_id=author_id,
            actor_type=author_type.value,
            detail=clean[:280],
        )
    )
    db.commit()
    db.refresh(comm)

    try:
        AuditService().log(
            actor_id=author_id,
            action="birthday.order.portal_message",
            entity_type="birthday_order",
            entity_id=order.id,
            metadata={"direction": direction.value, "issue_id": issue_id},
        )
    except Exception:  # noqa: BLE001 - best-effort
        pass

    if author_type == ActorType.SUPPLIER:
        try:
            NotificationService().notify_module_role(
                module_key="birthday", role="BIRTHDAY_ADMIN",
                type="birthday.portal_message",
                title=f"Supplier message on {order.order_reference}",
                body=clean[:280],
                related_entity_type="birthday_order", related_entity_id=order.id,
            )
        except Exception:  # noqa: BLE001 - best-effort
            pass

    return comm


# --- Unified Timeline -------------------------------------------------------

# Event types a supplier is allowed to see in the merged timeline. Lifecycle
# and communication only — never internal detection / address / audit noise.
_SUPPLIER_VISIBLE_EVENT_TYPES = frozenset(
    {"STATUS_CHANGE", "ORDER_CHANGED_POST_RELEASE", "DELIVERY_DATE_ADJUSTED", "EMAIL_SENT", "PORTAL_MESSAGE"}
)
_CHANNEL_BADGE = {
    CommunicationChannel.EMAIL.value: "Email",
    CommunicationChannel.PORTAL.value: "Portal",
    CommunicationChannel.SYSTEM.value: "System",
}


@dataclass
class TimelineEntry:
    at: datetime
    kind: str  # "message" | "email" | "event" | "issue"
    channel: str | None
    direction: str | None
    author_type: str | None
    author_id: int | None
    title: str
    body: str | None
    meta: dict


def _author_label(author_type: str | None) -> str:
    return {
        "USER": "Internal",
        "SUPPLIER": "Supplier",
        "SYSTEM": "System",
    }.get(author_type or "", author_type or "System")


def build_timeline(db: Session, order: BirthdayOrder, *, audience: str) -> list[TimelineEntry]:
    """``audience`` is ``"internal"`` (everything) or ``"supplier"``
    (lifecycle + conversation only, no internal notes / audit / detection
    events)."""
    supplier_view = audience == "supplier"
    entries: list[TimelineEntry] = []

    comms = db.execute(
        select(SupplierCommunication).where(SupplierCommunication.order_id == order.id)
    ).scalars().all()
    for c in comms:
        is_email = c.channel == CommunicationChannel.EMAIL.value
        entries.append(
            TimelineEntry(
                at=c.received_at or c.sent_at or c.created_at,
                kind="email" if is_email else "message",
                channel=_CHANNEL_BADGE.get(c.channel, c.channel),
                direction=c.direction,
                author_type=c.author_type,
                author_id=c.author_id,
                title=(
                    f"{_author_label(c.author_type)} · {'Email' if is_email else 'Portal message'}"
                    + (f" — {c.subject}" if is_email and c.subject else "")
                ),
                body=c.body or None,
                meta={
                    "status": c.status,
                    "message_id": c.message_id,
                    "issue_id": c.issue_id,
                    "last_error": c.last_error if not supplier_view else None,
                },
            )
        )

    for e in db.execute(select(OrderEvent).where(OrderEvent.order_id == order.id)).scalars().all():
        if supplier_view and e.event_type not in _SUPPLIER_VISIBLE_EVENT_TYPES:
            continue
        if supplier_view and e.event_type == "PORTAL_MESSAGE":
            continue  # already represented by the SupplierCommunication row
        entries.append(
            TimelineEntry(
                at=e.created_at,
                kind="event",
                channel="System",
                direction=None,
                author_type=e.actor_type,
                author_id=e.actor_id,
                title=e.event_type.replace("_", " ").title(),
                body=e.detail,
                meta={"from_status": e.from_status, "to_status": e.to_status},
            )
        )

    for issue in db.execute(select(OrderIssue).where(OrderIssue.order_id == order.id)).scalars().all():
        entries.append(
            TimelineEntry(
                at=issue.created_at,
                kind="issue",
                channel=None,
                direction=None,
                author_type=issue.raised_by_type,
                author_id=issue.raised_by_id,
                title=f"Issue opened — {issue.type}",
                body=issue.detail,
                meta={"issue_id": issue.id, "status": issue.status},
            )
        )
        if issue.status == OrderIssueStatus.RESOLVED.value and issue.resolved_at is not None:
            entries.append(
                TimelineEntry(
                    at=issue.resolved_at,
                    kind="issue",
                    channel=None,
                    direction=None,
                    author_type="USER",
                    author_id=issue.resolved_by,
                    title=f"Issue resolved — {issue.type}",
                    body=issue.resolution_detail,
                    meta={"issue_id": issue.id, "status": issue.status},
                )
            )

    entries.sort(key=lambda x: (x.at is None, x.at))
    return entries
