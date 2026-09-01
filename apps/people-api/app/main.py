from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, people
from app.core.config import get_settings

settings = get_settings()

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

app.include_router(health.router)
app.include_router(people.router)
