from auth_client_py import CorrelationIdMiddleware, assert_trust_anchors_safe
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, recruitment, webhooks
from app.core.config import get_settings

settings = get_settings()

# Fail closed: a non-development APP_ENV must not run with the shipped
# insecure secret defaults (see auth_client_py.security).
assert_trust_anchors_safe(
    settings.app_env,
    {
        "JWT_DEV_SECRET": settings.jwt_dev_secret,
        "INTERNAL_SERVICE_SECRET": settings.internal_service_secret,
    },
    database_url=settings.database_url,
)

app = FastAPI(
    title="DijiOne Recruitment Source API",
    description=(
        "The single DijiOne owner of direct Lever access (Architecture "
        "Completion Plan §3). Owns the Lever read models (postings, "
        "candidacies), the DijiOne standard source-sync lifecycle, and the "
        "governed DTC posting-tag parser. Consuming applications "
        "(DijiTalentFlow, DijiSpark) call this service's canonical API — "
        "never Lever directly. Lever is GET-only (CLAUDE.md §60)."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CorrelationIdMiddleware)

app.include_router(health.router)
app.include_router(recruitment.router)
app.include_router(webhooks.router)
