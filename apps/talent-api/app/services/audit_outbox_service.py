"""Durable delivery of reconcile audit events to Platform Core.

Inside ``audit_outbox_scope`` an audit event becomes a row in the caller's own
transaction, so it commits or rolls back with the change it records. Only the
reconcile opens that scope; every other workflow keeps best-effort delivery.

Delivery is at-least-once with a stable ``event_id``, which Platform Core uses
to record each event exactly once. This module imports nothing that can start
a reconcile or a sync.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.audit_outbox import DELIVERED, FAILED, PENDING, AuditOutbox

logger = logging.getLogger("talent-api.audit_outbox")

BATCH_SIZE = 100
CLAIM_SECONDS = 120
RUN_SECONDS = 240.0  # inside the job's 280 s replica timeout
BASE_RETRY_SECONDS = 30
MAX_RETRY_SECONDS = 3600
# Consecutive failures that mean Platform Core is down, not one bad event.
STOP_AFTER_FAILURES = 5
DELIVERED_RETENTION = timedelta(days=30)
CLEANUP_BATCH = 1000
_REQUEST_TIMEOUT = 10.0
_AUDIT_PATH = "/api/platform/internal/audit-events"

_session: ContextVar[Session | None] = ContextVar("audit_outbox_session", default=None)


@contextmanager
def audit_outbox_scope(db: Session) -> Iterator[None]:
    token = _session.set(db)
    try:
        yield
    finally:
        _session.reset(token)


def enqueue_if_in_scope(**event) -> bool:
    db = _session.get()
    if db is None:
        return False
    event_id = str(uuid.uuid4())
    db.add(AuditOutbox(event_id=event_id, payload=json.dumps({"event_id": event_id, **event}, default=str)))
    return True


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _build_client() -> httpx.Client:
    settings = get_settings()
    return httpx.Client(
        base_url=settings.platform_api_url.rstrip("/"),
        timeout=_REQUEST_TIMEOUT,
        headers={"X-Internal-Token": settings.internal_service_secret, "X-Internal-Caller": "talent-audit-outbox-job"},
    )


def claim_batch(db: Session, *, limit: int = BATCH_SIZE) -> list[tuple[int, str]]:
    """Lease due events. SKIP LOCKED keeps concurrent workers off the same rows."""
    now = _utcnow()
    rows = db.execute(
        select(AuditOutbox)
        .where(
            AuditOutbox.status == PENDING,
            AuditOutbox.next_attempt_at <= now,
            or_(AuditOutbox.claimed_until.is_(None), AuditOutbox.claimed_until <= now),
        )
        .order_by(AuditOutbox.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).scalars().all()
    for row in rows:
        row.claimed_until = now + timedelta(seconds=CLAIM_SECONDS)
        row.attempts += 1
        row.last_attempt_at = now
    claimed = [(row.id, row.payload) for row in rows]
    db.commit()
    return claimed


def _settle(db: Session, row_id: int, **values) -> None:
    """Only a still-pending row changes, so a worker whose claim expired cannot
    undo another worker's delivery."""
    db.execute(update(AuditOutbox).where(AuditOutbox.id == row_id, AuditOutbox.status == PENDING).values(
        claimed_until=None, **values
    ))
    db.commit()


def _retry_at(attempts: int, now: datetime) -> datetime:
    return now + timedelta(seconds=min(BASE_RETRY_SECONDS * 2 ** (attempts - 1), MAX_RETRY_SECONDS))


def _deliver(client: httpx.Client, event_id: str, payload: str) -> str | None:
    """None if Platform Core has the event; otherwise why not. Only an explicit
    acknowledgment of this event_id counts, so a Platform Core that does not
    support event_id is never mistaken for delivery."""
    try:
        response = client.post(_AUDIT_PATH, content=payload, headers={"Content-Type": "application/json"})
    except httpx.HTTPError as exc:
        return type(exc).__name__
    if response.status_code not in (200, 201):
        return f"http_{response.status_code}"
    try:
        acknowledged = response.json().get("event_id") == event_id
    except ValueError:
        acknowledged = False
    return None if acknowledged else "no_event_id_ack"


def _release(db: Session, row_ids: list[int]) -> None:
    if row_ids:
        db.execute(update(AuditOutbox).where(AuditOutbox.id.in_(row_ids), AuditOutbox.status == PENDING).values(
            claimed_until=None
        ))
        db.commit()


def drain(db: Session, *, client: httpx.Client | None = None, run_seconds: float = RUN_SECONDS) -> dict:
    """Deliver due events in bounded batches until none remain, time runs out,
    or Platform Core looks down. Undelivered events stay for a later run."""
    owned = client or _build_client()
    started = time.monotonic()
    delivered = retried = refused = streak = 0
    stopped = None
    try:
        while stopped is None:
            batch = claim_batch(db)
            if not batch:
                break
            for index, (row_id, payload) in enumerate(batch):
                if time.monotonic() - started > run_seconds:
                    stopped = "time_limit"
                elif streak >= STOP_AFTER_FAILURES:
                    stopped = "platform_unavailable"
                if stopped:
                    _release(db, [r for r, _ in batch[index:]])
                    break
                now = _utcnow()
                error = _deliver(owned, json.loads(payload)["event_id"], payload)
                if error is None:
                    _settle(db, row_id, status=DELIVERED, delivered_at=now, last_error=None)
                    delivered += 1
                    streak = 0
                elif error == "http_409":
                    _settle(db, row_id, status=FAILED, last_error=error)
                    refused += 1
                    streak = 0
                else:
                    attempts = db.execute(select(AuditOutbox.attempts).where(AuditOutbox.id == row_id)).scalar_one()
                    _settle(db, row_id, next_attempt_at=_retry_at(attempts, now), last_error=error)
                    db.commit()
                    retried += 1
                    streak += 1
    finally:
        if client is None:
            owned.close()
    purged = purge_delivered(db)
    return {"delivered": delivered, "retried": retried, "refused": refused, "purged": purged, "stopped": stopped,
            "elapsed_seconds": round(time.monotonic() - started, 1), **outbox_stats(db)}


def purge_delivered(db: Session) -> int:
    """Only delivered rows past retention go, a bounded number per run."""
    cutoff = _utcnow() - DELIVERED_RETENTION
    ids = db.execute(
        select(AuditOutbox.id).where(AuditOutbox.status == DELIVERED, AuditOutbox.delivered_at < cutoff)
        .limit(CLEANUP_BATCH)
    ).scalars().all()
    if ids:
        db.execute(delete(AuditOutbox).where(AuditOutbox.id.in_(ids)))
        db.commit()
    return len(ids)


def outbox_stats(db: Session) -> dict:
    counts = dict(db.execute(select(AuditOutbox.status, func.count()).group_by(AuditOutbox.status)).all())
    oldest = db.execute(select(func.min(AuditOutbox.created_at)).where(AuditOutbox.status == PENDING)).scalar()
    db.rollback()
    if oldest is not None and oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=UTC)
    return {
        "pending": counts.get(PENDING, 0),
        "failed": counts.get(FAILED, 0),
        "delivered_retained": counts.get(DELIVERED, 0),
        "oldest_pending_seconds": round((_utcnow() - oldest).total_seconds()) if oldest else None,
    }
