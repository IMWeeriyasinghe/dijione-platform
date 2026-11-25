"""Notifications go through Platform Core's in-app service. Each one is stored in
the outbox with the attendance change, so a Platform Core outage cannot fail that
change, and is retried until delivered. Text carries no times or employee names.

Staged reminder emails are sent via mail-client-py using an independent
AtworkReminderEmailSent table for at-most-once per session+stage+channel.
"""

import logging
import re
from datetime import datetime, timedelta

from auth_client_py import PlatformClient
from mail_client_py import MailClient, MailOutcome
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
from app.models.corrections import AttendanceEmployee, CorrectionRequest
from app.models.notifications import NotificationOutbox
from app.models.reminders import AtworkReminderEmailSent, AtworkReminderWatermark
from app.services.attendance_policy import AttendancePolicy
from app.services.employee_directory import employee_names
from app.services.reminder_email_templates import (
    render_stage1_email,
    render_stage2_email,
    render_stage3_email,
)
from app.services.reporting import Reporting

logger = logging.getLogger("atwork-api.notifications")

REVIEWERS = [PERM_MANAGEMENT_ACCESS, PERM_CORRECTIONS_REVIEW]
MAX_ATTEMPTS = 12
REMINDER_AFTER = timedelta(hours=24)
REMINDER_LOCAL_HOUR = 9
_MAX_REASON = 300

STAGE1_HOURS = 10
STAGE3_HOURS = 24

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


# ---------------------------------------------------------------------------
# Rollout watermark
# ---------------------------------------------------------------------------


def _get_watermark(db: Session, now: datetime) -> datetime:
    """Return the deploy-time watermark. If none exists yet (should not happen
    after migration), insert one for `now` so future runs find it."""
    row = db.get(AtworkReminderWatermark, 1)
    if row is not None:
        return row.watermark_at
    # Fallback: seed on first run (migration should have done this already).
    try:
        with db.begin_nested():
            db.add(AtworkReminderWatermark(id=1, watermark_at=now))
            db.flush()
    except IntegrityError:
        db.rollback()
        row = db.get(AtworkReminderWatermark, 1)
        if row:
            return row.watermark_at
    return now


# ---------------------------------------------------------------------------
# Email channel helpers
# ---------------------------------------------------------------------------


_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,253}\.[^@\s]{2,}$")
_SERVICE_PREFIXES = ("no-reply", "noreply", "donotreply", "do-not-reply", "mailer-daemon", "postmaster")


def _resolve_recipient(db: Session, user_id: int) -> str | None:
    """Return the Entra-sourced email for this employee from the DijiOne identity directory.

    AttendanceEmployee.email is written from claims.email (Entra JWT) by remember_employee()
    on every attendance action — it is the established trusted DijiOne identity mapping.
    Returns None when the address is absent, malformed, or matches a service-account pattern.
    """
    emp = db.get(AttendanceEmployee, user_id)
    if emp is None or not emp.email:
        return None
    email = emp.email.strip()
    lower = email.lower()
    # Must match a minimal but structurally valid address format.
    if not _EMAIL_RE.match(lower):
        return None
    # Reject well-known service account patterns.
    local = lower.split("@")[0]
    if any(local.startswith(p) for p in _SERVICE_PREFIXES):
        return None
    return email


def _claim_email(db: Session, session_id: str, stage: int, recipient: str) -> AtworkReminderEmailSent | None:
    """Atomically claim an email slot. Returns the row on success, None if already claimed."""
    existing = db.scalar(
        select(AtworkReminderEmailSent).where(
            AtworkReminderEmailSent.session_id == session_id,
            AtworkReminderEmailSent.stage == stage,
        )
    )
    if existing is not None:
        return None
    row = AtworkReminderEmailSent(session_id=session_id, stage=stage, recipient_email=recipient, status="PENDING")
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        db.rollback()
        return None
    return row


def _send_email(
    db: Session,
    mail: MailClient,
    row: AtworkReminderEmailSent,
    subject: str,
    html_body: str,
    now: datetime,
) -> bool:
    """Send the email and update the tracking row. Returns True on success."""
    if not row.recipient_email:
        row.status = "FAILED"
        db.commit()
        return False
    try:
        result = mail.send(to=row.recipient_email, subject=subject, body=html_body, content_type="HTML")
        if result.sent:
            row.status, row.sent_at = "SENT", now
            db.commit()
            return True
        # Blocked/disabled — not a retry-worthy outcome.
        if result.outcome in (MailOutcome.BLOCKED, MailOutcome.DISABLED):
            row.status = "FAILED"
            db.commit()
            return False
        # Submission error — schedule retry.
        row.attempts += 1
        row.next_attempt_at = now + timedelta(seconds=min(60 * 2**row.attempts, 3600))
        db.commit()
        return False
    except Exception:  # noqa: BLE001 - never let an email error block the scheduler
        logger.warning("Reminder email send raised", exc_info=False)
        row.attempts += 1
        row.next_attempt_at = now + timedelta(seconds=min(60 * 2**row.attempts, 3600))
        db.commit()
        return False


# ---------------------------------------------------------------------------
# Staged reminder state machine
# ---------------------------------------------------------------------------


def _enqueue_staged_reminders(
    db: Session,
    policy: AttendancePolicy,
    now: datetime,
    mail: MailClient,
    watermark: datetime,
) -> dict:
    """3-stage reminder workflow for sessions checked in AFTER the watermark.

    Stage 1 (10 h):  friendly in-app + email; no unverified flag.
    Stage 2 (threshold h): warning in-app + email; threshold = policy.missed_checkout_hours.
    Stage 3 (24 h):  final in-app + email + management visibility.

    Each stage fires at most once per session per channel (dedupe).
    Sessions that check out before delivery are skipped.
    """
    settings = get_settings()
    stage2_hours = policy.missed_checkout_hours
    stage1_cutoff = now - timedelta(hours=STAGE1_HOURS)

    # Fetch all OPEN sessions past stage1 threshold, started after watermark.
    stmt = (
        select(AttendanceSession)
        .where(
            AttendanceSession.status == STATUS_OPEN,
            AttendanceSession.check_in_at <= stage1_cutoff,
            AttendanceSession.check_in_at >= watermark,
        )
        .order_by(AttendanceSession.check_in_at)
    )
    sessions = list(db.scalars(stmt))
    if not sessions:
        return {"stage1": 0, "stage2": 0, "stage3": 0, "email_sent": 0}

    user_ids = {s.platform_user_id for s in sessions}
    names_map = employee_names(db, user_ids)

    s1_count = s2_count = s3_count = email_sent = 0

    for session in sessions:
        sid = session.id
        uid = session.platform_user_id
        emp = names_map.get(uid)
        full_name = emp.full_name if emp else f"User #{uid}"
        check_in = session.check_in_at
        zone = policy.zone
        zone_name = policy.business_time_zone
        link = "/atwork"

        elapsed_seconds = (now - check_in).total_seconds()
        elapsed_hours = elapsed_seconds / 3600
        recipient = _resolve_recipient(db, uid)

        # Catch-up sequencing: when a session first appears at a late stage, only send
        # one email (the highest applicable) so a 25h session doesn't flood the employee
        # with three simultaneous messages. In-app notifications are still deduped per
        # stage and are all fine to create; only the email channel needs suppression.
        # For normal incremental runs, lower-stage rows already exist (SENT), so
        # _claim_email returns None for them and only the new stage email is sent.
        if elapsed_hours >= STAGE3_HOURS:
            max_email_stage = 3
        elif elapsed_hours >= stage2_hours:
            max_email_stage = 2
        else:
            max_email_stage = 1

        # Stage 1 (>= 10 h)
        inapp_key1 = f"atwork:reminder:stage1:inapp:{sid}"
        inapp_added = _enqueue_once(
            db,
            inapp_key1,
            "ATWORK_REMINDER_STAGE1",
            "Your work session is still active",
            f"You have been checked in for over {STAGE1_HOURS} hours. If you have finished working, please check out.",
            link,
            user_id=uid,
        )
        s1_count += int(inapp_added)

        if max_email_stage == 1:
            email_row = _claim_email(db, sid, 1, recipient or "")
            if email_row and email_row.recipient_email:
                subject, html = render_stage1_email(
                    employee_name=full_name,
                    check_in_at=check_in,
                    zone=zone,
                    zone_name=zone_name,
                    app_url=settings.atwork_app_url,
                )
                if _send_email(db, mail, email_row, subject, html, now):
                    email_sent += 1
            elif email_row:
                email_row.status = "FAILED"
                db.commit()

        # Stage 2 (>= policy.missed_checkout_hours)
        if elapsed_hours >= stage2_hours:
            inapp_key2 = f"atwork:reminder:stage2:inapp:{sid}"
            inapp_added2 = _enqueue_once(
                db,
                inapp_key2,
                "ATWORK_REMINDER_STAGE2",
                "Possible missed check-out",
                (
                    f"Your session has been open for over {stage2_hours} hours. "
                    "The elapsed time is unverified until you check out or submit a correction."
                ),
                f"/atwork/requests/new?sessionId={sid}",
                user_id=uid,
            )
            s2_count += int(inapp_added2)

            if max_email_stage == 2:
                email_row2 = _claim_email(db, sid, 2, recipient or "")
                if email_row2 and email_row2.recipient_email:
                    subject2, html2 = render_stage2_email(
                        employee_name=full_name,
                        check_in_at=check_in,
                        zone=zone,
                        zone_name=zone_name,
                        threshold_hours=stage2_hours,
                        app_url=settings.atwork_app_url,
                    )
                    if _send_email(db, mail, email_row2, subject2, html2, now):
                        email_sent += 1
                elif email_row2:
                    email_row2.status = "FAILED"
                    db.commit()

        # Stage 3 (>= 24 h)
        if elapsed_hours >= STAGE3_HOURS:
            inapp_key3 = f"atwork:reminder:stage3:inapp:{sid}"
            inapp_added3 = _enqueue_once(
                db,
                inapp_key3,
                "ATWORK_REMINDER_STAGE3",
                "Attendance session still open — 24 h",
                "Your session has been open for over 24 hours. Your attendance manager has been notified.",
                f"/atwork/requests/new?sessionId={sid}",
                user_id=uid,
            )
            s3_count += int(inapp_added3)

            # Management visibility notification (one per session, to reviewers).
            mgmt_key = f"atwork:reminder:stage3:mgmt:{sid}"
            _enqueue_once(
                db,
                mgmt_key,
                "ATWORK_REMINDER_STAGE3_MGMT",
                "Open session — 24 h",
                f"{full_name} has an attendance session that has been open for over 24 hours.",
                f"/atwork/management/sessions/{sid}",
                reviewers=True,
                exclude=[uid],
            )

            # Stage 3 email is always the most relevant; always attempt it.
            email_row3 = _claim_email(db, sid, 3, recipient or "")
            if email_row3 and email_row3.recipient_email:
                subject3, html3 = render_stage3_email(
                    employee_name=full_name,
                    check_in_at=check_in,
                    zone=zone,
                    zone_name=zone_name,
                    app_url=settings.atwork_app_url,
                )
                if _send_email(db, mail, email_row3, subject3, html3, now):
                    email_sent += 1
            elif email_row3:
                email_row3.status = "FAILED"
                db.commit()

    return {"stage1": s1_count, "stage2": s2_count, "stage3": s3_count, "email_sent": email_sent}


# ---------------------------------------------------------------------------
# Email retry
# ---------------------------------------------------------------------------

RETRY_EMAIL_MAX_AGE = timedelta(days=7)


def _retry_pending_emails(db: Session, mail: MailClient, policy: AttendancePolicy, now: datetime) -> dict:
    """Retry PENDING email rows whose next_attempt_at has elapsed and whose session is still open.

    Skips rows whose session has been checked out since the original send attempt,
    marking them FAILED so they are not retried again. This is the sole path for
    recovering transient send failures — the initial _enqueue_staged_reminders only
    attempts once per claim.
    """
    rows = list(
        db.scalars(
            select(AtworkReminderEmailSent).where(
                AtworkReminderEmailSent.status == "PENDING",
                AtworkReminderEmailSent.next_attempt_at <= now,
                AtworkReminderEmailSent.created_at >= now - RETRY_EMAIL_MAX_AGE,
            )
        )
    )
    settings = get_settings()
    retried = cancelled = 0
    for row in rows:
        # Revalidate: session must still be open.
        session = db.scalar(
            select(AttendanceSession).where(
                AttendanceSession.id == row.session_id,
                AttendanceSession.status == STATUS_OPEN,
            )
        )
        if session is None:
            row.status = "FAILED"
            db.commit()
            cancelled += 1
            continue
        # Rebuild the email body from the still-open session state.
        uid = session.platform_user_id
        names = employee_names(db, {uid})
        emp = names.get(uid)
        full_name = emp.full_name if emp else f"User #{uid}"
        zone = policy.zone
        zone_name = policy.business_time_zone
        app_url = settings.atwork_app_url
        check_in = session.check_in_at
        kw = dict(employee_name=full_name, check_in_at=check_in, zone=zone, zone_name=zone_name, app_url=app_url)
        if row.stage == 1:
            subject, html = render_stage1_email(**kw)
        elif row.stage == 2:
            subject, html = render_stage2_email(**kw, threshold_hours=policy.missed_checkout_hours)
        else:
            subject, html = render_stage3_email(**kw)
        if _send_email(db, mail, row, subject, html, now):
            retried += 1
    return {"email_retried": retried, "email_cancelled": cancelled}


# ---------------------------------------------------------------------------
# Scheduled entry point
# ---------------------------------------------------------------------------


def enqueue_scheduled(db: Session, policy: AttendancePolicy, now: datetime, mail: MailClient | None = None) -> dict:
    """Safe to run at any frequency: each alert has one key, whatever the interval."""

    watermark = _get_watermark(db, now)

    # Legacy single-stage notification for pre-deploy sessions (check_in before watermark).
    missed = 0
    hours = policy.missed_checkout_hours
    for row in Reporting(db, policy, now).missed_checkouts():
        session = db.get(AttendanceSession, row["session_id"])
        if session and session.check_in_at >= watermark:
            continue  # post-deploy session handled by staged reminders below
        missed += _enqueue_once(
            db,
            f"atwork:missed-checkout:{row['session_id']}",
            "ATWORK_MISSED_CHECKOUT",
            "Check-out may have been missed",
            f"Your attendance session has been open for over {hours} hours. If you forgot to check out, request a correction.",
            f"/atwork/requests/new?sessionId={row['session_id']}",
            user_id=row["platform_user_id"],
        )

    # Staged 3-stage reminders for post-deploy sessions.
    staged = {"stage1": 0, "stage2": 0, "stage3": 0, "email_sent": 0}
    if mail is not None:
        staged = _enqueue_staged_reminders(db, policy, now, mail, watermark)
    else:
        # Fallback: stage2 in-app only (backward compat when mail not passed).
        staged = _enqueue_staged_reminders(
            db,
            policy,
            now,
            # NullMailTransport equivalent: a client that never sends.
            _null_mail_client(),
            watermark,
        )

    # Pending-correction daily reminder.
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

    # Retry any reminder emails that failed transiently and are now due.
    email_retry = {"email_retried": 0, "email_cancelled": 0}
    if mail is not None:
        email_retry = _retry_pending_emails(db, mail, policy, now)

    return {
        "missed_checkout": int(missed),
        "pending_reminder": int(reminders),
        **staged,
        **email_retry,
    }


def _null_mail_client() -> MailClient:
    from mail_client_py import DisabledPolicy, NullMailTransport

    return MailClient(transport=NullMailTransport(), policy=DisabledPolicy())


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
    if row.kind in (
        "ATWORK_MISSED_CHECKOUT",
        "ATWORK_REMINDER_STAGE1",
        "ATWORK_REMINDER_STAGE2",
        "ATWORK_REMINDER_STAGE3",
        "ATWORK_REMINDER_STAGE3_MGMT",
    ):
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
