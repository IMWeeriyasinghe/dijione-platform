from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import admin, health
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="DijiOne Admin API",
    description=(
        "DijiOne Admin Center. Owns no database — every request is "
        "authorized and persisted by Platform Core using the caller's own "
        "bearer token; DijiTalentFlow data is enriched in from talent-api, "
        "best-effort. See docs/platform/service-architecture.md."
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
app.include_router(admin.router)
