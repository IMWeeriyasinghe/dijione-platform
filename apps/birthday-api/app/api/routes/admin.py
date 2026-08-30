"""Admin-only, user-auth-gated surface for operational actions that
otherwise only exist behind the service-to-service internal secret (plan
§7). Calls the exact same ``run_daily_scan`` service the production
external scheduler and ``internal.py`` call — no detection logic is
duplicated here, this is purely an auth-appropriate wrapper for UAT/ops."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import BirthdayScope, require_birthday_permission
from app.api.routes.config import get_or_create_config
from app.api.routes.internal import _scan_run_to_dict
from app.db.session import get_db
from app.integrations.factory import get_bamboohr_client
from app.models.scan_run import ScanRun
from app.services.detection_service import run_daily_scan

router = APIRouter(prefix="/api/birthday/admin", tags=["birthday-admin"])


@router.post("/run-detection")
def run_detection(
    db: Session = Depends(get_db),
    _scope: BirthdayScope = Depends(require_birthday_permission("birthday.config.manage")),
) -> dict:
    config = get_or_create_config(db)
    client = get_bamboohr_client()
    return run_daily_scan(db, client, config, trigger="MANUAL")


@router.get("/scan-runs")
def list_scan_runs(
    limit: int = 20,
    db: Session = Depends(get_db),
    _scope: BirthdayScope = Depends(require_birthday_permission("birthday.config.manage")),
) -> list[dict]:
    """Same scan-run history as internal.py's service-to-service route,
    exposed to authenticated admin users so the internal UI can show it
    without needing the shared internal-service secret."""
    limit = max(1, min(limit, 100))
    runs = db.query(ScanRun).order_by(ScanRun.started_at.desc()).limit(limit).all()
    return [_scan_run_to_dict(r) for r in runs]
