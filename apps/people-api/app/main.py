from auth_client_py import CorrelationIdMiddleware, assert_trust_anchors_safe
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, people
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
    title="DijiOne People / Workforce API",
    description=(
        "The single DijiOne owner of direct BambooHR access (Architecture "
        "Completion Plan §3). Owns the employee/workforce read model and "
        "the DijiOne standard source-sync lifecycle. Consuming applications "
        "(DijiBirthday today) call this service's canonical API — never "
        "BambooHR directly. Never writes to BambooHR."
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
app.include_router(people.router)
