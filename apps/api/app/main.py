from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    auth,
    health,
    integrations,
    modules,
    notifications,
    talent_applications,
    talent_candidates,
    talent_clients,
    talent_dashboard,
    talent_documents,
    talent_interviews,
    talent_messages,
    talent_requests,
    webhooks,
)
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="DijiOne Platform API",
    description="Shared platform API for DijiOne and its modules (first module: DijiTalentFlow).",
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
app.include_router(auth.router)
app.include_router(modules.router)
app.include_router(notifications.router)
app.include_router(talent_clients.router)
app.include_router(talent_requests.router)
app.include_router(talent_candidates.router)
app.include_router(talent_applications.router)
app.include_router(talent_interviews.router)
app.include_router(talent_messages.router)
app.include_router(talent_documents.router)
app.include_router(talent_dashboard.router)
app.include_router(integrations.router)
app.include_router(webhooks.router)
