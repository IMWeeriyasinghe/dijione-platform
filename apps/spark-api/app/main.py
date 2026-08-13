from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, spark
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="DijiSpark API",
    description=(
        "DijiSpark service skeleton (CR §10) — proves DijiOne can host a "
        "third independently bounded application. No Spark Hire "
        "integration, no BambooHR report upload, no database yet; see "
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
app.include_router(spark.router)
