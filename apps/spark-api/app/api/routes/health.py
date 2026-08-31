from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"service": "spark-api", "status": "healthy"}


@router.get("/health/deep")
def health_deep() -> dict:
    """Readiness probe. spark-api is still a skeleton — no database, no
    business logic, no downstream dependency — so 'deep' just confirms the
    process is up and reports the environment."""
    return {
        "service": "spark-api",
        "status": "healthy",
        "checks": {"app_env": get_settings().app_env, "database": "none (skeleton)"},
    }
