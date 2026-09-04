from auth_client_py import CorrelationIdMiddleware, assert_trust_anchors_safe
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    health,
    recruitment,
    talent_applications,
    talent_candidates,
    talent_clients,
    talent_dashboard,
    talent_documents,
    talent_external,
    talent_external_admin,
    talent_interviews,
    talent_messages,
    talent_postings,
    talent_requests,
    talent_summary,
)
from app.core.config import get_settings

settings = get_settings()

# Fail closed: a non-development APP_ENV must not run with the shipped
# insecure secret defaults (see auth_client_py.security). The external
# magic-link session secret is a distinct trust anchor and is checked too.
assert_trust_anchors_safe(
    settings.app_env,
    {
        "JWT_DEV_SECRET": settings.jwt_dev_secret,
        "INTERNAL_SERVICE_SECRET": settings.internal_service_secret,
        "EXTERNAL_SESSION_JWT_SECRET": settings.external_session_jwt_secret,
    },
    database_url=settings.database_url,
)

app = FastAPI(
    title="DijiTalentFlow API",
    description=(
        "DijiTalentFlow — talent requests, candidates, applications, "
        "interviews, messages, documents, and the client-visibility trust "
        "decision (PostingClientMapping). Consumes the Recruitment Source "
        "domain (recruitment-api) over HTTP; holds no Lever or HubSpot "
        "credential itself. Authorizes purely from JWT claims issued by "
        "Platform Core; owns its own database. See "
        "docs/platform/service-architecture.md."
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
app.include_router(talent_summary.router)
app.include_router(talent_clients.router)
app.include_router(talent_requests.router)
app.include_router(talent_candidates.router)
app.include_router(talent_applications.router)
app.include_router(talent_interviews.router)
app.include_router(talent_messages.router)
app.include_router(talent_documents.router)
app.include_router(talent_dashboard.router)
app.include_router(talent_external.router)
app.include_router(talent_external_admin.router)
app.include_router(talent_postings.router)
app.include_router(recruitment.router)
app.include_router(recruitment.internal_router)
