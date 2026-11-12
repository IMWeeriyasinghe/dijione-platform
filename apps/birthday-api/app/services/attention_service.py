"""Attention / SLA + detection-health engine (Phase 1 §O).

Everything is computed on read (dashboard cards) and emitted once per run
by ``run_attention_sweep`` — driven by ``birthday-attention-job`` (daily).
Deterministic, no rules engine. Notifications are **digests** (one per rule
— "N orders overdue for verification"), so the daily cadence + digest form
are the dedupe; no ledger table needed. Scan success stays silent.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import OrderIssueStatus, ScanRunStatus
from app.models.inbound_email import InboundEmail
from app.models.order_issue import OrderIssue
from app.models.scan_run import ScanRun
from app.repositories.birthday_order_repository import BirthdayOrderRepository
from app.services.notification_service import NotificationService

_SCAN_STALE_HOURS = 26  # a daily scan older than this is a problem


def count_open_issues(db: Session) -> int:
    return db.execute(
        select(func.count()).select_from(OrderIssue).where(
            OrderIssue.status == OrderIssueStatus.OPEN.value
        )
    ).scalar_one()


def count_unmatched_emails(db: Session) -> int:
    return db.execute(
        select(func.count()).select_from(InboundEmail).where(InboundEmail.status == "UNMATCHED")
    ).scalar_one()


def scan_health(db: Session, *, now: datetime | None = None) -> dict:
    """Last-scan freshness + a trailing consecutive-deferral counter."""
    now = now or datetime.now(UTC)
    runs = db.execute(
        select(ScanRun).order_by(ScanRun.started_at.desc()).limit(20)
    ).scalars().all()
    last = runs[0] if runs else None

    consecutive_deferrals = 0
    for r in runs:
        if r.status == ScanRunStatus.DEFERRED_SOURCE_UNAVAILABLE.value:
            consecutive_deferrals += 1
        elif r.status == ScanRunStatus.COMPLETED.value:
            break

    last_started = last.started_at if last else None
    if last_started is not None and last_started.tzinfo is None:
        last_started = last_started.replace(tzinfo=UTC)
    stale = last_started is None or (now - last_started) > timedelta(hours=_SCAN_STALE_HOURS)

    return {
        "last_scan_at": last_started.isoformat() if last_started else None,
        "last_status": last.status if last else None,
        "consecutive_deferrals": consecutive_deferrals,
        "stale": bool(stale),
        "healthy": not stale and consecutive_deferrals == 0,
    }


def _notify(rule: str, title: str, body: str) -> None:
    try:
        NotificationService().notify_module_role(
            module_key="birthday", role="BIRTHDAY_ADMIN",
            type=f"birthday.attention.{rule}", title=title, body=body,
        )
    except Exception:  # noqa: BLE001
        pass


def run_attention_sweep(db: Session, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    today = now.date()
    repo = BirthdayOrderRepository(db)
    config = _get_config(db)
    sla_cutoff = now - timedelta(hours=config.acknowledgement_sla_hours)

    counts = {
        "verification_overdue": repo.count_verification_overdue(today=today),
        "acceptance_overdue": repo.count_acceptance_overdue(sla_cutoff=sla_cutoff),
        "deliveries_today_at_risk": repo.count_deliveries_today_at_risk(today=today),
        "overdue_delivery": repo.count_overdue_delivery(today=today),
        "on_hold": repo.count_on_hold(),
        "open_issues": count_open_issues(db),
        "unmatched_emails": count_unmatched_emails(db),
    }
    emitted: list[str] = []

    if counts["verification_overdue"]:
        _notify("verification_overdue", "Address verification overdue",
                f"{counts['verification_overdue']} order(s) are past their verify-by date.")
        emitted.append("verification_overdue")
    if counts["acceptance_overdue"]:
        _notify("acceptance_overdue", "Suppliers have not accepted orders",
                f"{counts['acceptance_overdue']} order(s) sent to a supplier are unaccepted "
                f"beyond the {config.acknowledgement_sla_hours}h SLA.")
        emitted.append("acceptance_overdue")
    if counts["deliveries_today_at_risk"]:
        _notify("deliveries_today_at_risk", "Deliveries at risk today",
                f"{counts['deliveries_today_at_risk']} order(s) are due today and not yet out for delivery.")
        emitted.append("deliveries_today_at_risk")
    if counts["overdue_delivery"]:
        _notify("overdue_delivery", "Overdue deliveries",
                f"{counts['overdue_delivery']} order(s) are past their delivery date and not complete.")
        emitted.append("overdue_delivery")
    if counts["on_hold"]:
        _notify("on_hold", "Orders on hold need a decision",
                f"{counts['on_hold']} order(s) are ON_HOLD (lead time too short) and need to be "
                "expedited, rescheduled, or cancelled.")
        emitted.append("on_hold")

    health = scan_health(db, now=now)
    if not health["healthy"]:
        detail = (
            f"consecutive deferrals: {health['consecutive_deferrals']}"
            if health["consecutive_deferrals"]
            else f"last scan: {health['last_scan_at'] or 'never'}"
        )
        _notify("detection_health", "Birthday detection is not running normally",
                f"Last status {health['last_status'] or 'none'}; {detail}.")
        emitted.append("detection_health")

    db.commit()
    return {"counts": counts, "scan_health": health, "notifications_emitted": emitted}


def _get_config(db: Session):
    from app.api.routes.config import get_or_create_config

    return get_or_create_config(db)
