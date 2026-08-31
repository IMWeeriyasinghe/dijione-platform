import httpx
from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"service": "admin-api", "status": "healthy"}


@router.get("/health/deep")
def health_deep() -> dict:
    """Readiness probe. admin-api owns no database — it is a zero-DB BFF —
    so 'deep' means: can it reach the two services it forwards to? Both
    checks are **non-fatal**: a TalentFlow outage must never break user/role
    administration (CR §38), and platform-api being briefly slow should not
    flap admin-api out of rotation."""
    settings = get_settings()
    checks: dict[str, object] = {}

    for name, url in (
        ("platform_api", f"{settings.platform_api_url}/health"),
        ("talent_api", f"{settings.talent_api_url}/health"),
    ):
        try:
            resp = httpx.get(url, timeout=2.0)
            checks[name] = "ok" if resp.status_code == 200 else f"http {resp.status_code}"
        except httpx.HTTPError:
            checks[name] = "unreachable"  # degraded, not fatal

    degraded = any(v != "ok" for v in checks.values())
    return {
        "service": "admin-api",
        "status": "degraded" if degraded else "healthy",
        "checks": checks,
    }
