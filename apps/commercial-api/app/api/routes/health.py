from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"service": "commercial-api", "status": "healthy"}


@router.get("/health/deep")
def health_deep(db: Session = Depends(get_db)) -> dict:
    """commercial-api is a skeleton — a webhook receiver + a mock HubSpot
    stub proving the seam, no canonical read model yet."""
    settings = get_settings()
    checks: dict[str, object] = {}
    ok = True
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {exc.__class__.__name__}"
        ok = False
    checks["integrations_mode"] = settings.integrations_mode
    return {"service": "commercial-api", "status": "healthy" if ok else "degraded", "checks": checks}
