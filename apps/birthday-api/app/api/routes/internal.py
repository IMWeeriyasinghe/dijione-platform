"""Service-to-service surface for triggering the daily BambooHR detection
scan (plan §12 Phase B / future-state plan §W Phase 1). Gated by the
shared internal-service secret, never a per-user token — mirrors
talent-api's ``/api/talent/internal`` routes.

Production automatic detection is an EXTERNAL scheduler (Azure Function
Timer / Logic App recurrence) calling ``POST /run-daily-scan`` daily —
there is deliberately no in-process scheduler here (decision C)."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_internal_service
from app.api.routes.config import get_or_create_config
from app.core.config import get_settings
from app.db.session import get_db
from app.integrations.factory import get_employee_source
from app.models.scan_run import ScanRun
from app.services import attention_service, inbound_email_service, order_email_service
from app.services.detection_service import run_daily_scan

router = APIRouter(prefix="/api/birthday/internal", tags=["birthday-internal"])


@router.post("/run-daily-scan")
def run_daily_scan_endpoint(
    db: Session = Depends(get_db), _service: None = Depends(require_internal_service)
) -> dict:
    """people-api unreachable -> run_daily_scan itself defers safely (see
    ScanRunStatus.DEFERRED_SOURCE_UNAVAILABLE) and returns 200 with that
    status rather than a 5xx — this is an expected, self-healing outcome,
    not a failure of the endpoint."""
    config = get_or_create_config(db)
    client = get_employee_source()
    return run_daily_scan(db, client, config, trigger="SCHEDULED")


@router.post("/run-comms")
def run_comms_endpoint(
    db: Session = Depends(get_db), _service: None = Depends(require_internal_service)
) -> dict:
    """Driven by ``birthday-comms-job`` (~10 min): automatic outbound-email
    backoff retry, and (Phase 1 §1.5) inbound supplier-email polling."""
    return {
        "email_retry": order_email_service.retry_failed_outbound(db),
        "inbound_email": inbound_email_service.poll(db),
    }


@router.post("/run-attention")
def run_attention_endpoint(
    db: Session = Depends(get_db), _service: None = Depends(require_internal_service)
) -> dict:
    """Driven by ``birthday-attention-job`` (daily): the SLA / attention /
    detection-health sweep (§O). Emits digest notifications to
    BIRTHDAY_ADMIN; scan success stays silent."""
    return attention_service.run_attention_sweep(db)


class _DevInboundEmail(BaseModel):
    from_address: str
    subject: str = ""
    body: str = ""
    in_reply_to: str | None = None
    provider_message_id: str | None = None


@router.post("/dev/inbound-email")
def dev_inject_inbound_email(
    payload: _DevInboundEmail,
    db: Session = Depends(get_db),
    _service: None = Depends(require_internal_service),
) -> dict:
    """DEV-only: feed a supplier email reply straight into the ingestion
    pipeline (correlation / sender validation / quarantine), so §1.5 is
    provable in hosted DEV without a real mailbox. 404 unless
    EMAIL_SENDING_MODE=mock (mirrors the dev supplier-persona routes)."""
    if get_settings().email_sending_mode != "mock":
        raise HTTPException(status_code=404, detail="Not found")
    from app.integrations.inbound_mail.client import InboundMessage

    msg = InboundMessage(
        id=payload.provider_message_id or f"dev-{datetime.now(UTC).timestamp()}",
        from_address=payload.from_address,
        subject=payload.subject,
        body_text=payload.body,
        received_at=datetime.now(UTC),
        in_reply_to=[payload.in_reply_to] if payload.in_reply_to else [],
    )
    outcome = inbound_email_service.ingest_message(db, msg)
    return {"outcome": outcome, "provider_message_id": msg.id}


def _scan_run_to_dict(run: ScanRun) -> dict:
    import json

    return {
        "run_id": run.run_id,
        "trigger": run.trigger,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "employees_scanned": run.employees_scanned,
        "orders_created": run.orders_created,
        "orders_existing": run.orders_existing,
        "exceptions": run.exceptions,
        "ineligible_skipped": run.ineligible_skipped,
        "errors": json.loads(run.errors_json or "[]"),
    }


@router.get("/scan-runs")
def list_scan_runs(
    limit: int = 20,
    db: Session = Depends(get_db),
    _service: None = Depends(require_internal_service),
) -> list[dict]:
    """Scan-run history (plan §U) — replaces the previous 501. Ordered
    newest-first so an operator/dashboard sees the latest run first."""
    limit = max(1, min(limit, 100))
    runs = (
        db.query(ScanRun)
        .order_by(ScanRun.started_at.desc())
        .limit(limit)
        .all()
    )
    return [_scan_run_to_dict(r) for r in runs]


@router.get("/scan-runs/{run_id}")
def get_scan_run(
    run_id: str,
    db: Session = Depends(get_db),
    _service: None = Depends(require_internal_service),
) -> dict:
    run = db.query(ScanRun).filter(ScanRun.run_id == run_id).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Scan run not found")
    return _scan_run_to_dict(run)
