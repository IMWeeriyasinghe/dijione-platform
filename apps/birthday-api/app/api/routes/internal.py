"""Service-to-service surface for triggering the daily BambooHR detection
scan (plan §12 Phase B / future-state plan §W Phase 1). Gated by the
shared internal-service secret, never a per-user token — mirrors
talent-api's ``/api/talent/internal`` routes.

Production automatic detection is an EXTERNAL scheduler (Azure Function
Timer / Logic App recurrence) calling ``POST /run-daily-scan`` daily —
there is deliberately no in-process scheduler here (decision C)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_internal_service
from app.api.routes.config import get_or_create_config
from app.db.session import get_db
from app.integrations.factory import get_bamboohr_client
from app.models.scan_run import ScanRun
from app.services.detection_service import run_daily_scan

router = APIRouter(prefix="/api/birthday/internal", tags=["birthday-internal"])


@router.post("/run-daily-scan")
def run_daily_scan_endpoint(
    db: Session = Depends(get_db), _service: None = Depends(require_internal_service)
) -> dict:
    config = get_or_create_config(db)
    client = get_bamboohr_client()
    return run_daily_scan(db, client, config, trigger="SCHEDULED")


def _scan_run_to_dict(run: ScanRun) -> dict:
    import json

    return {
        "run_id": run.run_id,
        "trigger": run.trigger,
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
