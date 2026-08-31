"""people-api is an internal-only service: only DijiOne backends call it,
always with the shared internal token. Tests run against SQLite with
``INTEGRATIONS_MODE=mock`` — no BambooHR credential, no network.
"""

import os
import sys
from pathlib import Path

# Honour a pre-set DATABASE_URL (the `postgres` CI workflow points this at
# a real Postgres 16); fall back to a local SQLite file otherwise.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_people.db")
os.environ["API_CORS_ORIGINS"] = "http://localhost:3000"
os.environ["INTERNAL_SERVICE_SECRET"] = "test-only-internal-secret"
os.environ["INTEGRATIONS_MODE"] = "mock"
os.environ["PLATFORM_API_URL"] = "http://127.0.0.1:1"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app


def internal_headers() -> dict:
    return {"X-Internal-Token": os.environ["INTERNAL_SERVICE_SECRET"]}


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def api_client():
    return TestClient(app)
