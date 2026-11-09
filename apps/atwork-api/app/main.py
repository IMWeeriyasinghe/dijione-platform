from auth_client_py import CorrelationIdMiddleware, assert_trust_anchors_safe
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import attendance, atwork, health
from app.core.config import get_settings
from app.core.errors import AttendanceError, attendance_error_handler

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
    title="DijiAtWork API",
    description="DijiAtWork module foundation. Verifies DijiOne signed claims locally and owns its attendance database.",
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
app.include_router(atwork.router)
app.include_router(attendance.router)

app.add_exception_handler(AttendanceError, attendance_error_handler)
