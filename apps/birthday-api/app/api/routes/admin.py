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
from app.db.session import get_db
from app.integrations.factory import get_bamboohr_client
from app.services.detection_service import run_daily_scan

router = APIRouter(prefix="/api/birthday/admin", tags=["birthday-admin"])


@router.post("/run-detection")
def run_detection(
    db: Session = Depends(get_db),
    _scope: BirthdayScope = Depends(require_birthday_permission("birthday.config.manage")),
) -> dict:
    config = get_or_create_config(db)
    client = get_bamboohr_client()
    return run_daily_scan(db, client, config)
