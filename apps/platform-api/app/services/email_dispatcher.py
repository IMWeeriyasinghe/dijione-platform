"""Email outbox dispatcher for platform-api.

Sends queued ``email_outbox`` rows through ``packages/mail-client-py`` with platform-api's
own configuration (its own managed identity when MAIL_TRANSPORT=graph). Runs in-process on a
background thread (no new Azure resource) and on demand from Admin > Notifications.

Replica safety: a row is claimed with a conditional UPDATE (``PENDING|RETRY -> SENDING``);
only the replica whose UPDATE changed the row sends it. A claim left behind by a crashed
replica is released after ``email_claim_lease_seconds``. Delivery is therefore at-least-once:
a crash between Graph accepting a message and the row being marked could, rarely, send it
twice. Never at-most-zero for a committed change.

Outcomes are recorded truthfully: SUBMITTED means Microsoft Graph accepted the message
(202), not that it was delivered.
"""

from __future__ import annotations

import logging
import threading
from collections import Counter
from datetime import timedelta

from mail_client_py import (
    DisabledPolicy,
    GraphMailTransport,
    InternalAllowlistPolicy,
    MailClient,
    MailOutcome,
    MailPolicy,
    MailTransport,
    NullMailTransport,
    ProductionPolicy,
    backoff_seconds,
    is_retryable,
    render_email,
)
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.base import utcnow
from app.models.email_notification import EmailOutbox, EmailTestRecipient, OutboxStatus
from app.services import access_notifications

logger = logging.getLogger(__name__)

PRODUCTION_ENVIRONMENTS = ("prod", "production")
_OUTCOME_STATUS = {
    MailOutcome.SUBMITTED: OutboxStatus.SUBMITTED,
    MailOutcome.SIMULATED: OutboxStatus.SIMULATED,
    MailOutcome.BLOCKED: OutboxStatus.BLOCKED,
    MailOutcome.DISABLED: OutboxStatus.DISABLED,
}

_transport_cache: dict[tuple, MailTransport] = {}
_transport_override: MailTransport | None = None


def set_transport_override(transport: MailTransport | None) -> None:
    """Tests only: replace the configured transport."""
    global _transport_override
    _transport_override = transport


def _transport(settings: Settings) -> MailTransport:
    if _transport_override is not None:
        return _transport_override
    if settings.mail_transport != "graph":
        return NullMailTransport()
    key = (settings.mail_shared_mailbox, settings.graph_base_url)
    if key not in _transport_cache:
        _transport_cache[key] = GraphMailTransport(sender_mailbox=settings.mail_shared_mailbox,
                                                   base_url=settings.graph_base_url)
    return _transport_cache[key]


def effective_policy_name(settings: Settings) -> str:
    """The recipient policy actually applied. Fail closed: an unknown name, or "production"
    outside a production environment, is "disabled"."""
    if settings.mail_transport != "graph":
        return "simulated"
    if settings.mail_policy == "internal_allowlist":
        return "internal_allowlist"
    if settings.mail_policy == "production" and settings.app_env.lower() in PRODUCTION_ENVIRONMENTS:
        return "production"
    return "disabled"


def active_test_recipients(session: Session) -> list[str]:
    return list(session.execute(select(EmailTestRecipient.address).where(EmailTestRecipient.active.is_(True))).scalars())


def build_policy(session: Session, settings: Settings) -> MailPolicy:
    name = effective_policy_name(settings)
    if name == "simulated":
        # The null transport can never send a real email; let the flow run end to end.
        return ProductionPolicy()
    if name == "internal_allowlist":
        return InternalAllowlistPolicy(active_test_recipients(session))
    if name == "production":
        return ProductionPolicy()
    return DisabledPolicy()


def _release_stale_claims(session: Session, settings: Settings) -> None:
    cutoff = utcnow() - timedelta(seconds=settings.email_claim_lease_seconds)
    session.execute(
        update(EmailOutbox)
        .where(EmailOutbox.status == OutboxStatus.SENDING, EmailOutbox.claimed_at < cutoff)
        .values(status=OutboxStatus.RETRY, claimed_at=None, last_error="released: dispatcher claim expired")
    )
    session.commit()


def _claim(session: Session, row_id: int) -> bool:
    result = session.execute(
        update(EmailOutbox)
        .where(EmailOutbox.id == row_id, EmailOutbox.status.in_(OutboxStatus.DISPATCHABLE))
        .values(status=OutboxStatus.SENDING, claimed_at=utcnow())
    )
    session.commit()
    return result.rowcount == 1


def _render(row: EmailOutbox, settings: Settings):
    if row.template_key != access_notifications.TEMPLATE_KEY:
        raise ValueError(f"unknown template {row.template_key!r}")
    portal = settings.public_base_url.rstrip("/") + "/" if settings.public_base_url else None
    return render_email(access_notifications.render_access_email(row, portal_url=portal))


def send_one(session: Session, row: EmailOutbox, settings: Settings) -> str:
    """Send a claimed row and record the outcome. Returns the new status."""
    now = utcnow()
    if not access_notifications.event_enabled(session, row.event_type):
        row.status, row.completed_at, row.claimed_at = OutboxStatus.SKIPPED, now, None
        row.last_error = "event switched off in Admin > Notifications"
        session.commit()
        return row.status

    try:
        rendered = _render(row, settings)
        client = MailClient(transport=_transport(settings), policy=build_policy(session, settings))
        result = client.send(to=row.recipient_email, subject=row.subject, body=rendered.html,
                             correlation_id=row.correlation_id, content_type="HTML")
        outcome, error, request_id = result.outcome, result.error, result.graph_request_id
    except Exception as exc:  # noqa: BLE001 - a bad row must not stop the dispatcher
        outcome, error, request_id = MailOutcome.FAILED, f"{type(exc).__name__}: {exc}", None

    row.attempts = (row.attempts or 0) + 1
    row.last_attempt_at = now
    row.claimed_at = None
    row.transport_outcome = str(outcome)
    row.graph_request_id = request_id
    row.last_error = (error or "")[:1000] or None
    if is_retryable(outcome):
        if row.attempts >= row.max_attempts:
            row.status, row.completed_at = OutboxStatus.FAILED, now
        else:
            row.status = OutboxStatus.RETRY
            row.not_before = now + timedelta(
                seconds=backoff_seconds(row.attempts, base=settings.email_retry_base_seconds,
                                        cap=settings.email_retry_cap_seconds)
            )
    else:
        row.status, row.completed_at = _OUTCOME_STATUS.get(outcome, OutboxStatus.FAILED), now
    session.commit()
    # Correlation id and status only: no address or content in logs.
    logger.info("email %s %s attempt=%s", row.correlation_id, row.status, row.attempts)
    return row.status


def dispatch_due(session_factory: sessionmaker | None = None, *, limit: int | None = None) -> dict[str, int]:
    """Send every due row (up to ``limit``). Returns counts by resulting status."""
    if session_factory is None:
        from app.db.session import SessionLocal as session_factory  # noqa: N813
    settings = get_settings()
    counts: Counter[str] = Counter()
    with session_factory() as session:
        _release_stale_claims(session, settings)
        ids = list(
            session.execute(
                select(EmailOutbox.id)
                .where(EmailOutbox.status.in_(OutboxStatus.DISPATCHABLE), EmailOutbox.not_before <= utcnow())
                .order_by(EmailOutbox.not_before, EmailOutbox.id)
                .limit(limit or settings.email_dispatch_batch_size)
            ).scalars()
        )
        for row_id in ids:
            if not _claim(session, row_id):
                continue
            row = session.get(EmailOutbox, row_id)
            session.refresh(row)
            counts[send_one(session, row, settings)] += 1
    return dict(counts)


class DispatcherThread:
    """The in-process loop: backfill once, then dispatch every interval. Never raises."""

    def __init__(self, interval_seconds: int):
        self._interval = max(interval_seconds, 5)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="email-dispatcher", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        from app.db.session import SessionLocal

        try:
            with SessionLocal() as session:
                added = access_notifications.backfill_snapshots(session)
                if added:
                    logger.info("access snapshot baseline recorded for %s users", added)
                realigned = access_notifications.rebaseline_snapshots(session)
                if realigned:
                    logger.info("access snapshots silently realigned for %s users", realigned)
        except Exception:  # noqa: BLE001
            logger.exception("access snapshot backfill failed; will rely on silent baselines")
        while not self._stop.wait(self._interval):
            try:
                dispatch_due(SessionLocal)
            except Exception:  # noqa: BLE001
                logger.exception("email dispatch cycle failed")
