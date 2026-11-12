"""Notifications go through Platform Core's in-app service. Each one is stored in
the outbox with the attendance change, so a Platform Core outage cannot fail that
change, and is retried until delivered. Text carries no times or employee names."""

import logging
from datetime import datetime, timedelta

from auth_client_py import PlatformClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import (
    CORRECTION_PENDING,
    MODULE_ATWORK,
    PERM_CORRECTIONS_REVIEW,
    PERM_MANAGEMENT_ACCESS,
    SERVICE_NAME,
    STATUS_OPEN,
)
from app.db.base import utcnow
from app.models.attendance import AttendanceSession
from app.models.corrections import CorrectionRequest
from app.models.notifications import NotificationOutbox
from app.services.attendance_policy import AttendancePolicy
from app.services.reporting import Reporting

logger = logging.getLogger("atwork-api.notifications")

REVIEWERS = [PERM_MANAGEMENT_ACCESS, PERM_CORRECTIONS_REVIEW]
MAX_ATTEMPTS = 12
REMINDER_AFTER = timedelta(hours=24)
REMINDER_LOCAL_HOUR = 9
_MAX_REASON = 300


# Platform Core scales to zero and can take well over a few seconds to start.
DELIVERY_TIMEOUT_SECONDS = 30.0
RETRY_FAILED_MAX_AGE = timedelta(days=7)
_STOP_AFTER_FAILURES = 3  # keeps a run within the job timeout when Platform Core is down


def platform_client() -> PlatformClient:
    settings = get_settings()
    return PlatformClient(
        settings.platform_api_url, settings.internal_service_secret, timeout=DELIVERY_TIMEOUT_SECONDS, caller=SERVICE_NAME
    )


def enqueue(
    db: Session,
    key: str,
    kind: str,
    title: str,
    body: str,
    link: str,
    *,
    user_id: int | None = None,
    reviewers: bool = False,
    exclude: list[int] | None = None,
) -> None:
    db.add(
        NotificationOutbox(
            dedupe_key=key,
            kind=kind,
            title=title,
            body=body,
            link_url=link,
            user_id=user_id,
            required_permissions=REVIEWERS if reviewers else None,
            exclude_user_ids=exclude or None,
            status="PENDING",
            attempts=0,
        )
    )


def correction_requested(db: Session, item: CorrectionRequest) -> None:
    enqueue(
        db,
        f"atwork:correction:{item.id}:requested",
        "ATWORK_CORRECTION_REQUESTED",
        "Attendance correction awaiting review",
        "A correction request needs your review.",
        f"/atwork/management/corrections/{item.id}",
        reviewers=True,
        exclude=[item.platform_user_id],
    )


def correction_approved(db: Session, item: CorrectionRequest) -> None:
    enqueue(
        db,
        f"atwork:correction:{item.id}:approved",
        "ATWORK_CORRECTION_APPROVED",
        "Attendance correction approved",
        "Your correction request was approved and your attendance has been updated.",
        "/atwork/requests",
        user_id=item.platform_user_id,
    )


def correction_rejected(db: Session, item: CorrectionRequest) -> None:
    reason = " ".join((item.decision_note or "").split())[:_MAX_REASON]
    enqueue(
        db,
        f"atwork:correction:{item.id}:rejected",
        "ATWORK_CORRECTION_REJECTED",
        "Attendance correction rejected",
        f"Your correction request was rejected. Reason: {reason}",
        "/atwork/requests",
        user_id=item.platform_user_id,
    )


def correction_withdrawn(db: Session, item: CorrectionRequest) -> None:
    enqueue(
        db,
        f"atwork:correction:{item.id}:withdrawn",
        "ATWORK_CORRECTION_WITHDRAWN",
        "Attendance correction withdrawn",
        "A pending correction request was withdrawn and no longer needs review.",
        "/atwork/management/corrections",
        reviewers=True,
        exclude=[item.platform_user_id],
    )


def _enqueue_once(db: Session, key: str, *args, **kwargs) -> bool:
    if db.scalar(select(NotificationOutbox.id).where(NotificationOutbox.dedupe_key == key)):
        return False
    try:
        with db.begin_nested():
            enqueue(db, key, *args, **kwargs)
            db.flush()
    except IntegrityError:  # another run got there first
        return False
    return True


def enqueue_scheduled(db: Session, policy: AttendancePolicy, now: datetime) -> dict:
    """Safe to run at any frequency: each alert has one key, whatever the interval."""
    missed = 0
    hours = policy.missed_checkout_hours
    for row in Reporting(db, policy, now).missed_checkouts():
        missed += _enqueue_once(
            db,
            f"atwork:missed-checkout:{row['session_id']}",
            "ATWORK_MISSED_CHECKOUT",
            "Check-out may have been missed",
            f"Your attendance session has been open for over {hours} hours. If you forgot to check out, request a correction.",
            f"/atwork/requests/new?sessionId={row['session_id']}",
            user_id=row["platform_user_id"],
        )
    reminders = 0
    local = now.astimezone(policy.zone)
    if local.hour >= REMINDER_LOCAL_HOUR:
        waiting = (
            db.scalar(
                select(func.count())
                .select_from(CorrectionRequest)
                .where(CorrectionRequest.status == CORRECTION_PENDING, CorrectionRequest.created_at <= now - REMINDER_AFTER)
            )
            or 0
        )
        if waiting:
            noun = "request has" if waiting == 1 else "requests have"
            reminders += _enqueue_once(
                db,
                f"atwork:pending-reminder:{local.date().isoformat()}",
                "ATWORK_CORRECTION_REMINDER",
                "Attendance corrections awaiting review",
                f"{waiting} correction {noun} been waiting for more than 24 hours.",
                "/atwork/management/corrections",
                reviewers=True,
            )
    db.commit()
    return {"missed_checkout": int(missed), "pending_reminder": int(reminders)}


def _payload(row: NotificationOutbox) -> dict:
    payload = {"dedupe_key": row.dedupe_key, "type": row.kind, "title": row.title, "body": row.body, "link_url": row.link_url}
    if row.user_id is not None:
        return {**payload, "user_id": row.user_id}
    return {
        **payload,
        "module_key": MODULE_ATWORK,
        "required_permissions": row.required_permissions,
        "exclude_user_ids": row.exclude_user_ids or [],
    }


def deliver_pending(db: Session, client: PlatformClient, now: datetime, limit: int = 100) -> dict:
    """SKIP LOCKED keeps two workers off one row; Platform Core's key covers a lost
    response. Delivery is therefore at-least-once with one visible result."""
    ids = list(
        db.scalars(
            select(NotificationOutbox.id)
            .where(NotificationOutbox.status == "PENDING", NotificationOutbox.next_attempt_at <= now)
            .order_by(NotificationOutbox.created_at)
            .limit(limit)
        )
    )
    db.rollback()
    sent = failed = consecutive_failures = 0
    for row_id in ids:
        if consecutive_failures >= _STOP_AFTER_FAILURES:
            break  # Platform Core is unavailable; the rest wait for the next run
        row = db.scalars(
            select(NotificationOutbox)
            .where(NotificationOutbox.id == row_id, NotificationOutbox.status == "PENDING")
            .with_for_update(skip_locked=True)
        ).first()
        if row is None:
            db.rollback()
            continue
        try:
            delivered = client.deliver_notification(_payload(row))
        except Exception:  # noqa: BLE001 - never let delivery escape
            logger.warning("Notification delivery raised", exc_info=False)
            delivered = False
        if delivered:
            row.status, row.sent_at = "SENT", now
            sent += 1
            consecutive_failures = 0
        else:
            row.attempts += 1
            failed += 1
            consecutive_failures += 1
            if row.attempts >= MAX_ATTEMPTS:
                row.status = "FAILED"
            else:
                row.next_attempt_at = now + timedelta(seconds=min(60 * 2**row.attempts, 3600))
        db.commit()
    return {"sent": sent, "failed": failed}


def _still_relevant(db: Session, row: NotificationOutbox, policy: AttendancePolicy, now: datetime) -> bool:
    """A failed notification is resent only if it is still true today."""
    parts = row.dedupe_key.split(":")
    if row.kind == "ATWORK_MISSED_CHECKOUT":
        session = db.get(AttendanceSession, parts[-1])
        return session is not None and session.status == STATUS_OPEN
    if row.kind == "ATWORK_CORRECTION_REMINDER":
        return parts[-1] == now.astimezone(policy.zone).date().isoformat()
    item = db.get(CorrectionRequest, parts[2]) if len(parts) > 3 else None
    if item is None:
        return False
    if row.kind == "ATWORK_CORRECTION_REQUESTED":
        return item.status == CORRECTION_PENDING
    return True  # a decision or withdrawal stays true once made


def retry_failed(db: Session, policy: AttendancePolicy, now: datetime) -> dict:
    """Requeue recent FAILED notifications that are still relevant. Platform Core's
    per-recipient key means an earlier, unconfirmed success is never shown twice."""
    rows = list(
        db.scalars(
            select(NotificationOutbox).where(
                NotificationOutbox.status == "FAILED", NotificationOutbox.created_at >= now - RETRY_FAILED_MAX_AGE
            )
        )
    )
    requeued = skipped = 0
    for row in rows:
        if _still_relevant(db, row, policy, now):
            row.status, row.attempts, row.next_attempt_at = "PENDING", 0, now
            requeued += 1
        else:
            skipped += 1
    db.commit()
    return {"requeued": requeued, "skipped": skipped}


def deliver_after_response() -> None:
    """Prompt delivery after a request. Anything left is picked up by the job."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        deliver_pending(db, platform_client(), utcnow(), limit=20)
    except Exception:  # noqa: BLE001 - the response has already succeeded
        logger.warning("Prompt notification delivery skipped", exc_info=False)
        db.rollback()
    finally:
        db.close()
