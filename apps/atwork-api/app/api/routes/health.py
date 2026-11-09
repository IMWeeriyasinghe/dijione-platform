from pathlib import Path

from auth_client_py import alembic_head_status
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import SERVICE_NAME
from app.db.session import get_db

router = APIRouter(tags=["health"])

_ALEMBIC_DIR = str(Path(__file__).resolve().parents[3] / "alembic")


@router.get("/health")
def health() -> dict:
    return {"service": SERVICE_NAME, "status": "healthy"}


@router.get("/health/deep")
def health_deep(db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    checks: dict[str, object] = {"app_env": settings.app_env, "integrations_mode": settings.integrations_mode}
    ok = True
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {exc.__class__.__name__}"
        ok = False
    try:
        revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        checks["migration"] = alembic_head_status(_ALEMBIC_DIR, revision)
    except Exception:  # noqa: BLE001
        checks["migration"] = {"current": "unknown", "head": "unknown", "up_to_date": None}
    return {"service": SERVICE_NAME, "status": "healthy" if ok else "degraded", "checks": checks}
