from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"service": "recruitment-api", "status": "healthy"}


@router.get("/health/deep")
def health_deep(db: Session = Depends(get_db)) -> dict:
    """Readiness: own database, applied migration revision, integrations
    mode. A Lever outage is reported by the sync-run freshness endpoint, not
    here — it must not take this service out of rotation for its consumers."""
    settings = get_settings()
    checks: dict[str, object] = {}
    ok = True

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {exc.__class__.__name__}"
        ok = False

    try:
        rev = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        checks["migration_revision"] = rev or "none"
    except Exception:  # noqa: BLE001
        checks["migration_revision"] = "unknown"

    checks["integrations_mode"] = settings.integrations_mode

    return {
        "service": "recruitment-api",
        "status": "healthy" if ok else "degraded",
        "checks": checks,
    }
