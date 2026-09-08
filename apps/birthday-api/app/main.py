from auth_client_py import CorrelationIdMiddleware, assert_trust_anchors_safe
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    admin,
    birthday,
    config,
    dashboard,
    dev_auth,
    employees,
    health,
    internal,
    orders,
    portal,
    supplier_auth_entra,
    suppliers,
)
from app.core.config import get_settings

settings = get_settings()

# Fail closed: a non-development APP_ENV must not run with the shipped
# insecure secret defaults (see auth_client_py.security). birthday-api also
# mints its own supplier-portal tokens with jwt_dev_secret.
assert_trust_anchors_safe(
    settings.app_env,
    {
        "JWT_DEV_SECRET": settings.jwt_dev_secret,
        "INTERNAL_SERVICE_SECRET": settings.internal_service_secret,
    },
    database_url=settings.database_url,
)

app = FastAPI(
    title="DijiBirthday API",
    description=(
        "DijiBirthday API — BambooHR-driven birthday-cake ordering: live "
        "employee-directory discovery, eligibility, idempotent detection, "
        "delivery-address verification, the explicit approval workflow, and "
        "the supplier-portal boundary. See docs/birthday/end-to-end-workflow.md."
    ),
    version="1.0.0",
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
app.include_router(birthday.router)
app.include_router(internal.router)
app.include_router(dashboard.router)
app.include_router(orders.router)
app.include_router(config.router)
app.include_router(suppliers.router)
app.include_router(employees.router)
app.include_router(portal.router)
app.include_router(dev_auth.router)
app.include_router(supplier_auth_entra.router)
app.include_router(admin.router)
