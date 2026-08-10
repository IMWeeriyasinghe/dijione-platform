import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_dijione.db"
os.environ["DEV_IDENTITY_MODE"] = "true"
os.environ["JWT_DEV_SECRET"] = "test-only-secret"
os.environ["INTEGRATIONS_MODE"] = "mock"
os.environ["API_CORS_ORIGINS"] = "http://localhost:3000"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.constants import MODULE_TALENT_FLOW, TalentFlowRole  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.user import User, UserModuleRole  # noqa: E402


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


@pytest.fixture()
def two_tenant_world(db):
    """Two clients, one client-user each, one TA member, one CS user."""
    abc = Client(name="ABC Company", industry="Financial Services", status="ACTIVE")
    xyz = Client(name="XYZ Company", industry="Retail", status="ACTIVE")
    db.add_all([abc, xyz])
    db.flush()

    abc_user = User(
        email="abc-user@example.com", full_name="ABC Client User", platform_role="PLATFORM_USER",
        persona_key="test-abc-client",
    )
    xyz_user = User(
        email="xyz-user@example.com", full_name="XYZ Client User", platform_role="PLATFORM_USER",
        persona_key="test-xyz-client",
    )
    ta_user = User(
        email="ta-user@example.com", full_name="TA User", platform_role="PLATFORM_USER",
        persona_key="test-ta",
    )
    cs_user = User(
        email="cs-user@example.com", full_name="CS User", platform_role="PLATFORM_USER",
        persona_key="test-cs",
    )
    db.add_all([abc_user, xyz_user, ta_user, cs_user])
    db.flush()

    db.add_all(
        [
            UserModuleRole(
                user_id=abc_user.id, module_key=MODULE_TALENT_FLOW,
                role=TalentFlowRole.TALENT_CLIENT.value, client_id=abc.id,
            ),
            UserModuleRole(
                user_id=xyz_user.id, module_key=MODULE_TALENT_FLOW,
                role=TalentFlowRole.TALENT_CLIENT.value, client_id=xyz.id,
            ),
            UserModuleRole(
                user_id=ta_user.id, module_key=MODULE_TALENT_FLOW, role=TalentFlowRole.TA_MEMBER.value
            ),
            UserModuleRole(
                user_id=cs_user.id, module_key=MODULE_TALENT_FLOW, role=TalentFlowRole.CUSTOMER_SUCCESS.value
            ),
        ]
    )
    db.commit()

    return {
        "abc": abc, "xyz": xyz,
        "abc_user": abc_user, "xyz_user": xyz_user, "ta_user": ta_user, "cs_user": cs_user,
    }


def auth_headers(api_client: TestClient, persona_key: str) -> dict:
    resp = api_client.post("/api/auth/dev-login", json={"persona_key": persona_key})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
