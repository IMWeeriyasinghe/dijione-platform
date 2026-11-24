"""Internal P&C email alerts for supplier activity in the Supplier Portal.

When the supplier posts a message, reports an issue, or says it cannot
fulfil an order, P&C gets an email so nobody has to watch the portal.

Reliability rules:
* The supplier's action is committed by the caller **before** this module
  runs. Everything here is best effort and never raises to the caller, so a
  mail outage can never lose a message/issue or fail the supplier request.
* One ``InternalAlert`` row per event per recipient, keyed on
  ``source_key`` + ``recipient`` (unique). Re-running for the same event is
  a no-op, so retries never send a second email.
* A FAILED send is retried by the ``birthday-comms-job`` sweep with the
  shared backoff, up to the shared maximum, then marked GAVE_UP.
* Mail goes through Birthday's own ``get_email_client`` and environment
  policy, so the DEV/UAT Email Safety allowlist applies unchanged
  (a non-allowlisted recipient is recorded as BLOCKED, never sent).
* Emails carry only operational facts: order reference, supplier, event,
  a short summary, the team member's name and a link to the order. Never
  the address or phone numbers.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta

from mail_client_py import EmailContent, EmailItem, MailOutcome, backoff_seconds, is_retryable, render_email
from mail_client_py.retry import DEFAULT_MAX_ATTEMPTS
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.factory import get_email_client
from app.models.birthday_order import BirthdayOrder
from app.models.detection_config import BirthdayDetectionConfig
from app.models.internal_alert import InternalAlert
from app.models.order_event import OrderEvent

logger = logging.getLogger(__name__)

APPLICATION_NAME = "DIJI Birthday"
EVENT_SUPPLIER_MESSAGE = "SUPPLIER_MESSAGE"
EVENT_SUPPLIER_ISSUE = "SUPPLIER_ISSUE"
EVENT_SUPPLIER_CANNOT_FULFIL = "SUPPLIER_CANNOT_FULFIL"

_SUMMARY_LIMIT = 280
_EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")
_TERMINAL_OUTCOMES = {MailOutcome.SUBMITTED, MailOutcome.SIMULATED}
_ISSUE_LABELS = {
    "CHANGE_REQUEST": "Change request",
    "CANNOT_FULFIL": "Cannot fulfil",
    "DELIVERY_ISSUE": "Delivery issue",
    "OTHER": "Other issue",
}


def parse_recipients(raw: str | None) -> list[str]:
    """Comma/semicolon/newline separated list -> unique, lower-cased emails."""
    seen: list[str] = []
    for part in re.split(r"[,;\n]", raw or ""):
        email = part.strip().lower()
        if email and email not in seen:
            seen.append(email)
    return seen


def invalid_recipients(raw: str | None) -> list[str]:
    return [e for e in parse_recipients(raw) if not _EMAIL.match(e)]


def _order_url(order: BirthdayOrder) -> str | None:
    base = (get_settings().birthday_internal_base_url or "").rstrip("/")
    return f"{base}/birthday/orders/{order.id}" if base else None


def _subject(event_type: str, order: BirthdayOrder) -> str:
    ref = order.order_reference
    if event_type == EVENT_SUPPLIER_MESSAGE:
        return f"{APPLICATION_NAME} — New supplier message for {ref}"
    if event_type == EVENT_SUPPLIER_CANNOT_FULFIL:
        return f"{APPLICATION_NAME} — Supplier unable to fulfil {ref}"
    return f"{APPLICATION_NAME} — Supplier issue reported for {ref}"


def _render(event_type: str, order: BirthdayOrder, *, summary: str, issue_type: str | None):
    supplier = order.supplier.name if order.supplier else "Supplier"
    if event_type == EVENT_SUPPLIER_MESSAGE:
        heading, event_label = "New message from the supplier", "Supplier message"
        action = "Read the message and reply from the order page."
    elif event_type == EVENT_SUPPLIER_CANNOT_FULFIL:
        heading, event_label = "The supplier cannot fulfil this order", "Cannot fulfil"
        action = "Arrange another supplier or update the order. It now needs attention."
    else:
        heading = "The supplier reported an issue"
        event_label = _ISSUE_LABELS.get(issue_type or "", "Issue")
        action = "Review the issue on the order page and resolve it."
    url = _order_url(order)
    content = EmailContent(
        application_name=APPLICATION_NAME,
        heading=heading,
        paragraphs=[f"{supplier} has raised this through the Supplier Portal.", action],
        items=[
            EmailItem(label="Order", detail=order.order_reference),
            EmailItem(label="Team member", detail=order.employee_name),
            EmailItem(label="Supplier", detail=supplier),
            EmailItem(label="Event", detail=event_label),
            EmailItem(label="Summary", detail=summary[:_SUMMARY_LIMIT]),
        ],
        action_label="Open the order" if url else None,
        action_url=url,
        footer_note="You receive this because you are on the DIJI Birthday operational alert list.",
    )
    return render_email(content)


def _recipients(db: Session) -> list[str]:
    config = db.query(BirthdayDetectionConfig).first()
    return [e for e in parse_recipients(config.ops_alert_recipients if config else None) if _EMAIL.match(e)]


def _send_one(db: Session, alert: InternalAlert, now: datetime) -> None:
    alert.attempts = (alert.attempts or 0) + 1
    try:
        result = get_email_client(db).send(
            to=alert.recipient, subject=alert.subject, body=alert.body,
            correlation_id=f"birthday-alert-{alert.id}-{alert.attempts}", content_type="HTML",
        )
    except Exception as exc:  # noqa: BLE001 - recorded, retried
        alert.status, alert.transport_outcome = "FAILED", MailOutcome.FAILED.value
        alert.last_error = str(exc)[:500]
    else:
        alert.transport_outcome = result.outcome.value
        alert.correlation_id = result.correlation_id
        if result.outcome in _TERMINAL_OUTCOMES:
            alert.status = "SENT" if result.outcome == MailOutcome.SUBMITTED else "SIMULATED"
            alert.sent_at, alert.last_error, alert.next_retry_at = now, None, None
            return
        alert.status = result.outcome.value  # BLOCKED / DISABLED / FAILED
        alert.last_error = (getattr(result, "error", None) or result.outcome.value)[:500]
        if not is_retryable(result.outcome):
            alert.next_retry_at = None
            return
    if alert.attempts >= DEFAULT_MAX_ATTEMPTS:
        alert.status, alert.next_retry_at = "GAVE_UP", None
    else:
        alert.next_retry_at = now + timedelta(seconds=backoff_seconds(alert.attempts))


def notify_supplier_activity(
    db: Session, order: BirthdayOrder, *, event_type: str, source_key: str,
    summary: str, issue_type: str | None = None,
) -> int:
    """Create (idempotently) and send the alert for one supplier event.
    Returns the number of alert rows created. Never raises."""
    try:
        recipients = _recipients(db)
        if not recipients:
            return 0
        subject = _subject(event_type, order)
        rendered = _render(event_type, order, summary=summary, issue_type=issue_type)
        existing = set(
            db.execute(
                select(InternalAlert.recipient).where(InternalAlert.source_key == source_key)
            ).scalars()
        )
        created: list[InternalAlert] = []
        for recipient in recipients:
            if recipient in existing:
                continue
            alert = InternalAlert(
                order_id=order.id, event_type=event_type, source_key=source_key,
                recipient=recipient, subject=subject[:255], body=rendered.html, status="PENDING",
            )
            db.add(alert)
            try:
                db.flush()
            except IntegrityError:  # a concurrent call created it first
                db.rollback()
                continue
            created.append(alert)
        now = datetime.now(UTC)
        for alert in created:
            _send_one(db, alert, now)
        if created:
            sent = sum(1 for a in created if a.status in ("SENT", "SIMULATED"))
            db.add(
                OrderEvent(
                    order_id=order.id, event_type="INTERNAL_ALERT", actor_type="SYSTEM",
                    actor_display_name="DIJI Birthday",
                    detail=f"P&C alerted by email ({event_type}): {sent}/{len(created)} sent",
                )
            )
        db.commit()
        return len(created)
    except Exception:  # noqa: BLE001 - never fail the supplier's action
        logger.exception("Internal alert for %s on order %s could not be processed", event_type, order.id)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return 0


def retry_failed_alerts(db: Session, *, now: datetime | None = None) -> dict:
    """Comms-job sweep: re-send FAILED alerts whose backoff has elapsed."""
    now = now or datetime.now(UTC)
    due = list(
        db.execute(
            select(InternalAlert).where(
                InternalAlert.status == "FAILED",
                InternalAlert.next_retry_at.is_not(None),
                InternalAlert.next_retry_at <= now,
            )
        ).scalars()
    )
    for alert in due:
        _send_one(db, alert, now)
    db.commit()
    return {"retried": len(due)}
