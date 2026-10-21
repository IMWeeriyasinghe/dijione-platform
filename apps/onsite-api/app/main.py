from auth_client_py import CorrelationIdMiddleware, assert_trust_anchors_safe
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import admin, health, onsite
from app.core.config import get_settings

settings = get_settings()

# Fail closed: a non-development APP_ENV must not run with the shipped
# insecure secret defaults (see auth_client_py.security).
assert_trust_anchors_safe(
    settings.app_env,
    {
        "PLATFORM_JWT_SECRET": settings.platform_jwt_secret,
        "INTERNAL_SERVICE_SECRET": settings.internal_service_secret,
    },
    database_url=settings.database_url,
)

app = FastAPI(
    title="Diji On-site API",
    description=(
        "Diji On-site application module. Mirrors raw attendance events from the "
        "separate ingestion plane's Azure SQL `onsite` schema (SELECT-only) into its "
        "own database, and serves neutral attendance facts. Depends only on "
        "platform-api and the people-api Workforce Directory — see docs/onsite/architecture.md."
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
app.include_router(onsite.router)
app.include_router(admin.router)
