from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import birthday, health
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="DijiBirthday API",
    description=(
        "DijiBirthday service skeleton (CR §9) — proves DijiOne can host a "
        "second independently bounded application. No BambooHR connection, "
        "no cake-ordering logic, no database yet; see "
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

app.include_router(health.router)
app.include_router(birthday.router)
