"""Service-to-service surface for triggering the daily BambooHR detection
scan (plan §12 Phase B). Gated by the shared internal-service secret, never
a per-user token — mirrors talent-api's ``/api/talent/internal`` routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_internal_service
from app.api.routes.config import get_or_create_config
from app.db.session import get_db
from app.integrations.factory import get_bamboohr_client
from app.services.detection_service import run_daily_scan

router = APIRouter(prefix="/api/birthday/internal", tags=["birthday-internal"])


@router.post("/run-daily-scan")
def run_daily_scan_endpoint(
    db: Session = Depends(get_db), _service: None = Depends(require_internal_service)
) -> dict:
    config = get_or_create_config(db)
    client = get_bamboohr_client()
    return run_daily_scan(db, client, config)


@router.get("/scan-runs/{run_id}")
def get_scan_run(run_id: str, _service: None = Depends(require_internal_service)) -> dict:
    """No dedicated ScanRun table exists in the Phase A data model (plan
    §12 scope) — run summaries are only available synchronously from the
    ``run-daily-scan`` response itself for now."""
    raise HTTPException(
        status_code=501,
        detail=(
            "Scan run history is not implemented — scan run details are "
            "available only via the run-daily-scan response for now."
        ),
    )
