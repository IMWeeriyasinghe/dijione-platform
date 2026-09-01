import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"service": "talent-api", "status": "healthy"}


@router.get("/health/deep")
def health_deep(db: Session = Depends(get_db)) -> dict:
    """Readiness probe for a deployed environment: database reachability,
    applied migration revision, and integrations mode."""
    settings = get_settings()
    checks: dict[str, object] = {}
    ok = True

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 - report, don't crash the probe
        checks["database"] = f"error: {exc.__class__.__name__}"
        ok = False

    try:
        rev = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        checks["migration_revision"] = rev or "none"
    except Exception:  # noqa: BLE001
        checks["migration_revision"] = "unknown"

    checks["integrations_mode"] = settings.integrations_mode

    # Recruitment Source (recruitment-api) reachability — NON-FATAL. A
    # source-domain outage degrades the recruitment screens but must never
    # take talent-api out of rotation (the fail-closed client-visibility
    # decision runs entirely from local tables).
    try:
        resp = httpx.get(f"{settings.recruitment_api_url}/health", timeout=2.0)
        checks["recruitment_source"] = "ok" if resp.status_code == 200 else f"http {resp.status_code}"
    except httpx.HTTPError:
        checks["recruitment_source"] = "degraded"

    return {"service": "talent-api", "status": "healthy" if ok else "degraded", "checks": checks}
