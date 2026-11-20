from contextlib import asynccontextmanager

from auth_client_py import CorrelationIdMiddleware, assert_trust_anchors_safe
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    app_access,
    auth,
    auth_entra,
    health,
    modules,
    notifications,
    platform_admin,
    platform_directory,
    platform_internal,
    view_as,
)
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



@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Starts the in-process email outbox dispatcher (docs/platform/email-notifications.md).
    Sending itself stays off unless MAIL_TRANSPORT=graph and a policy allows it."""
    dispatcher = None
    if settings.email_dispatcher_enabled:
        from app.services.email_dispatcher import DispatcherThread

        dispatcher = DispatcherThread(settings.email_dispatch_interval_seconds)
        dispatcher.start()
    yield
    if dispatcher is not None:
        dispatcher.stop()


app = FastAPI(
    lifespan=lifespan,
    title="DijiOne Platform Core API",
    description=(
        "Owns DijiOne identity, authorization, the module registry, audit log "
        "and notifications. Every other DijiOne service (Admin, DijiTalentFlow, "
        "DijiBirthday, DijiSpark) depends on this service for who a user is and "
        "what they may do — see docs/platform/service-architecture.md."
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
# Added last -> outermost: tags every request with a correlation id before
# anything else sees it, echoes it on the response, and it propagates on
# outbound internal calls (auth_client_py clients).
app.add_middleware(CorrelationIdMiddleware)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(auth_entra.router)
app.include_router(modules.router)
app.include_router(notifications.router)
app.include_router(platform_admin.router)
app.include_router(platform_directory.router)
app.include_router(platform_internal.router)
app.include_router(view_as.router)
app.include_router(app_access.router)
