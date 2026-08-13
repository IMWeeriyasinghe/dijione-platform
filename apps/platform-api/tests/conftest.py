import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_platform.db"
os.environ["DEV_IDENTITY_MODE"] = "true"
os.environ["JWT_DEV_SECRET"] = "test-only-secret"
os.environ["API_CORS_ORIGINS"] = "http://localhost:3000"
os.environ["INTERNAL_SERVICE_SECRET"] = "test-only-internal-secret"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.constants import MODULE_TALENT_FLOW  # noqa: E402
from app.core.permissions import ALL_PERMISSIONS, ALL_ROLES  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.role import Permission, Role, RolePermission  # noqa: E402
from app.models.user import User, UserModuleRole  # noqa: E402
from app.models.user_module_client_scope import UserModuleClientScope  # noqa: E402

ABC_CLIENT_ID = 1
XYZ_CLIENT_ID = 2
NOVA_CLIENT_ID = 3


def _seed_authorization_catalog(session) -> None:
    """Every test DB needs the Role/Permission catalog populated — it is
    the sole source of resolved permissions (see AuthorizationService)."""
    permission_ids: dict[str, int] = {}
    for perm in ALL_PERMISSIONS:
        row = Permission(
            key=perm.key, name=perm.name, description=perm.description,
            module_key=perm.module_key, category=perm.category,
        )
        session.add(row)
        session.flush()
        permission_ids[perm.key] = row.id
    for role_def in ALL_ROLES:
        role = Role(
            module_key=role_def.module_key, key=role_def.key, name=role_def.name,
            description=role_def.description, is_system=True,
        )
        session.add(role)
        session.flush()
        for perm_key in role_def.permissions:
            session.add(RolePermission(role_id=role.id, permission_id=permission_ids[perm_key]))
    session.commit()


def assign_client_scope(session, module_role: UserModuleRole, *, client_id: int | None) -> None:
    """Test helper mirroring scripts/seed.py's ``_assign_client_scope``."""
    if client_id is not None:
        session.add(
            UserModuleClientScope(
                user_module_role_id=module_role.id, client_id=client_id, all_clients=False
            )
        )
    else:
        session.add(UserModuleClientScope(user_module_role_id=module_role.id, all_clients=True))
    session.commit()


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        _seed_authorization_catalog(session)
        yield session
    finally:
        session.close()


@pytest.fixture()
def api_client():
    return TestClient(app)


@pytest.fixture()
def two_tenant_world(db):
    """Two "clients" (opaque ids — the Client rows themselves live in
    talent-api's database), one client-user each, one TA member, one CS
    user, plus a SUPER_ADMIN and a PLATFORM_ADMIN for admin-surface tests."""
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
    super_admin = User(
        email="super-admin@example.com", full_name="Super Admin", platform_role="SUPER_ADMIN",
        persona_key="test-super-admin",
    )
    platform_admin = User(
        email="platform-admin@example.com", full_name="Platform Admin", platform_role="PLATFORM_ADMIN",
        persona_key="test-platform-admin",
    )
    db.add_all([abc_user, xyz_user, ta_user, cs_user, super_admin, platform_admin])
    db.flush()

    db.add_all(
        [
            UserModuleRole(
                user_id=abc_user.id, module_key=MODULE_TALENT_FLOW,
                role="TALENT_CLIENT", client_id=ABC_CLIENT_ID,
            ),
            UserModuleRole(
                user_id=xyz_user.id, module_key=MODULE_TALENT_FLOW,
                role="TALENT_CLIENT", client_id=XYZ_CLIENT_ID,
            ),
            UserModuleRole(user_id=ta_user.id, module_key=MODULE_TALENT_FLOW, role="TA_MEMBER"),
            UserModuleRole(user_id=cs_user.id, module_key=MODULE_TALENT_FLOW, role="CUSTOMER_SUCCESS"),
        ]
    )
    db.commit()

    return {
        "abc_user": abc_user, "xyz_user": xyz_user, "ta_user": ta_user, "cs_user": cs_user,
        "super_admin": super_admin, "platform_admin": platform_admin,
    }


def auth_headers(api_client: TestClient, persona_key: str) -> dict:
    resp = api_client.post("/api/auth/dev-login", json={"persona_key": persona_key})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def internal_headers() -> dict:
    return {"X-Internal-Token": os.environ["INTERNAL_SERVICE_SECRET"]}
