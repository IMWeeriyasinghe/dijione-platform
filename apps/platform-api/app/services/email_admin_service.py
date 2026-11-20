"""Admin > Notifications: delivery history, retry, event switches, DEV/UAT test recipients.

Every change here is audited. Rendering details (``last_error``) are shown only to platform
administrators; nothing here exposes email bodies, which are rebuilt from template data.
"""

from __future__ import annotations

import re
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import utcnow
from app.models.email_notification import EmailOutbox, EmailTestRecipient, NotificationEventSetting, OutboxStatus
from app.services import access_notifications
from app.services.admin_service import ConflictError, NotFoundError
from app.services.audit_service import AuditService
from app.services.email_dispatcher import PRODUCTION_ENVIRONMENTS, effective_policy_name

_ADDRESS = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")  # one person's address; never a whole domain
APPLICATIONS = {access_notifications.APPLICATION_KEY: access_notifications.APPLICATION_NAME}


class InvalidInputError(ValueError):
    pass


def _row_out(row: EmailOutbox, *, detail: bool = False) -> dict:
    out = {
        "id": row.id,
        "correlation_id": row.correlation_id,
        "application_key": row.application_key,
        "application_name": APPLICATIONS.get(row.application_key, row.application_key),
        "event_type": row.event_type,
        "recipient_email": row.recipient_email,
        "recipient_user_id": row.recipient_user_id,
        "subject": row.subject,
        "status": row.status,
        "attempts": row.attempts,
        "max_attempts": row.max_attempts,
        "transport_outcome": row.transport_outcome,
        "created_at": row.created_at,
        "not_before": row.not_before,
        "last_attempt_at": row.last_attempt_at,
        "completed_at": row.completed_at,
        "can_retry": row.status in OutboxStatus.RETRYABLE_BY_ADMIN,
    }
    if detail:
        out |= {
            "last_error": row.last_error,
            "graph_request_id": row.graph_request_id,
            "superseded_by_id": row.superseded_by_id,
            "template_data": row.template_data,
        }
    return out


class EmailAdminService:
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService(db)

    # --- history ---------------------------------------------------------------------------

    def list_outbox(self, *, application: str | None = None, event_type: str | None = None,
                    recipient: str | None = None, status: str | None = None,
                    limit: int = 100, offset: int = 0) -> dict:
        stmt = select(EmailOutbox)
        if application:
            stmt = stmt.where(EmailOutbox.application_key == application)
        if event_type:
            stmt = stmt.where(EmailOutbox.event_type == event_type)
        if recipient:
            stmt = stmt.where(func.lower(EmailOutbox.recipient_email).contains(recipient.strip().lower()))
        if status:
            stmt = stmt.where(EmailOutbox.status == status)
        total = self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        rows = self.db.execute(
            stmt.order_by(EmailOutbox.id.desc()).limit(min(max(limit, 1), 500)).offset(max(offset, 0))
        ).scalars()
        return {"total": total, "items": [_row_out(r) for r in rows]}

    def get(self, outbox_id: int) -> dict:
        row = self.db.get(EmailOutbox, outbox_id)
        if row is None:
            raise NotFoundError("Notification not found")
        return _row_out(row, detail=True)

    def summary(self) -> dict:
        counts = dict(self.db.execute(select(EmailOutbox.status, func.count()).group_by(EmailOutbox.status)).all())
        settings = get_settings()
        return {
            "counts": {s: counts.get(s, 0) for s in OutboxStatus.ALL},
            "environment": settings.app_env,
            "transport": settings.mail_transport if settings.mail_transport == "graph" else "null",
            "configured_policy": settings.mail_policy,
            "effective_policy": effective_policy_name(settings),
            "is_production": settings.app_env.lower() in PRODUCTION_ENVIRONMENTS,
            "sender_mailbox": settings.mail_shared_mailbox or None,
            "access_notifications_enabled": settings.access_notifications_enabled,
            "dispatcher_enabled": settings.email_dispatcher_enabled,
            "applications": [{"key": k, "name": v} for k, v in APPLICATIONS.items()],
            "statuses": list(OutboxStatus.ALL),
        }

    def retry(self, *, actor, outbox_id: int) -> dict:
        row = self.db.get(EmailOutbox, outbox_id)
        if row is None:
            raise NotFoundError("Notification not found")
        if row.status not in OutboxStatus.RETRYABLE_BY_ADMIN:
            raise ConflictError(f"A {row.status} notification cannot be retried")
        if not access_notifications.is_still_accurate(self.db, row):
            raise ConflictError("This notification no longer matches the person's current access, so it "
                                "will not be re-sent. A newer change is (or will be) notified instead.")
        previous = row.status
        row.status = OutboxStatus.PENDING
        row.attempts = 0
        row.not_before = utcnow()
        row.completed_at = None
        row.claimed_at = None
        self.audit.log(actor_id=actor.id, action="email_notification.retried", entity_type="EmailOutbox",
                       entity_id=row.id, previous_state={"status": previous}, new_state={"status": row.status},
                       metadata={"correlation_id": row.correlation_id})
        self.db.commit()
        return _row_out(row, detail=True)

    # --- events ------------------------------------------------------------------------------

    def list_events(self) -> list[dict]:
        rows = {r.event_type: r for r in self.db.execute(select(NotificationEventSetting)).scalars()}
        return [
            {"event_type": key, "application_key": access_notifications.APPLICATION_KEY,
             "subject": f"[{access_notifications.APPLICATION_NAME}] | {purpose}", "description": description,
             "enabled": rows[key].enabled if key in rows else True}
            for key, (purpose, description) in access_notifications.EVENTS.items()
        ]

    def set_event(self, *, actor, event_type: str, enabled: bool) -> list[dict]:
        if event_type not in access_notifications.EVENTS:
            raise NotFoundError("Unknown notification event")
        row = self.db.get(NotificationEventSetting, event_type)
        previous = True if row is None else row.enabled
        if row is None:
            row = NotificationEventSetting(event_type=event_type)
            self.db.add(row)
        row.enabled = enabled
        row.updated_by_user_id = actor.id
        self.audit.log(actor_id=actor.id, action="notification_event.updated", entity_type="NotificationEvent",
                       entity_id=0, previous_state={"enabled": previous}, new_state={"enabled": enabled},
                       metadata={"event_type": event_type})
        self.db.commit()
        return self.list_events()

    # --- test recipients ----------------------------------------------------------------------

    def list_recipients(self) -> list[dict]:
        rows = self.db.execute(select(EmailTestRecipient).order_by(EmailTestRecipient.address)).scalars()
        return [{"id": r.id, "address": r.address, "label": r.label, "active": r.active, "created_at": r.created_at}
                for r in rows]

    def add_recipient(self, *, actor, address: str, label: str = "") -> list[dict]:
        address = (address or "").strip().lower()
        if not _ADDRESS.match(address):
            raise InvalidInputError("Enter one person's full email address (whole domains are not allowed)")
        existing = self.db.execute(select(EmailTestRecipient).where(EmailTestRecipient.address == address)).scalar()
        if existing is not None:
            if existing.active:
                raise ConflictError("That recipient is already on the list")
            existing.active = True
            entity_id = existing.id
        else:
            row = EmailTestRecipient(address=address, label=(label or "").strip()[:255], created_by_user_id=actor.id)
            self.db.add(row)
            self.db.flush()
            entity_id = row.id
        self.audit.log(actor_id=actor.id, action="email_test_recipient.added", entity_type="EmailTestRecipient",
                       entity_id=entity_id, new_state={"address": address})
        self.db.commit()
        return self.list_recipients()

    def remove_recipient(self, *, actor, recipient_id: int) -> list[dict]:
        row = self.db.get(EmailTestRecipient, recipient_id)
        if row is None:
            raise NotFoundError("Recipient not found")
        self.audit.log(actor_id=actor.id, action="email_test_recipient.removed", entity_type="EmailTestRecipient",
                       entity_id=row.id, previous_state={"address": row.address})
        self.db.delete(row)
        self.db.commit()
        return self.list_recipients()

    def recent_failures(self, *, hours: int = 24) -> int:
        cutoff = utcnow() - timedelta(hours=hours)
        return self.db.execute(
            select(func.count()).where(EmailOutbox.status == OutboxStatus.FAILED, EmailOutbox.updated_at >= cutoff)
        ).scalar_one()
