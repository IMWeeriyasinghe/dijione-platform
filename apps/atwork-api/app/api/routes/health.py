from fastapi import APIRouter

from app.core.config import get_settings
from app.core.constants import SERVICE_NAME

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"service": SERVICE_NAME, "status": "healthy"}


@router.get("/health/deep")
def health_deep() -> dict:
    """Readiness probe. The foundation has no database or downstream
    dependency, so this confirms the process is up and reports its mode."""
    settings = get_settings()
    return {
        "service": SERVICE_NAME,
        "status": "healthy",
        "checks": {
            "app_env": settings.app_env,
            "integrations_mode": settings.integrations_mode,
            "database": "none (foundation)",
        },
    }
