from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import commercial, health, webhooks
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="DijiOne Commercial / CRM API",
    description=(
        "Architectural seam for the Commercial/CRM domain (Architecture "
        "Completion Plan §3, Wave F) — the future single DijiOne owner of "
        "HubSpot. Skeleton today: a mock-only HubSpot stub and a webhook "
        "receiver proving the boundary, no live client, no canonical "
        "company/contact read model, no credential requested. It does NOT "
        "own canonical Client identity — that is platform-owned (§6.1)."
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

app.include_router(health.router)
app.include_router(commercial.router)
app.include_router(webhooks.router)
