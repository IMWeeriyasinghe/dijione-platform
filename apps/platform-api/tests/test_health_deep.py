"""/health/deep readiness probe: DB, migration revision, auth mode, and the
client-scope integrity check — a local join against the platform-owned
``clients`` table (Architecture Completion Plan §6.1)."""

from app.core.constants import MODULE_TALENT_FLOW
from app.models.user import User, UserModuleRole
from app.models.user_module_client_scope import UserModuleClientScope
from tests.conftest import ABC_CLIENT_ID, assign_client_scope


def _add_scope(db, *, client_id: int | None = None, client_ref: str | None = None) -> None:
    user = User(
        email=f"u{client_id}{client_ref}@example.com", full_name="U", platform_role="PLATFORM_USER",
        persona_key=f"x{client_id}{client_ref}",
    )
    db.add(user)
    db.flush()
    mr = UserModuleRole(user_id=user.id, module_key=MODULE_TALENT_FLOW, role="TA_MEMBER")
    db.add(mr)
    db.flush()
    if client_ref is not None:
        db.add(
            UserModuleClientScope(
                user_module_role_id=mr.id, client_id=client_id, client_ref=client_ref,
                all_clients=False,
            )
        )
        db.commit()
    else:
        assign_client_scope(db, mr, client_id=client_id)


def test_health_deep_ok(api_client, db):
    resp = api_client.get("/health/deep")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["auth_mode"] == "dev"
    assert body["checks"]["client_scope_integrity"] == "ok"  # no scope rows yet


def test_health_deep_ok_with_valid_scope(api_client, db):
    _add_scope(db, client_id=ABC_CLIENT_ID)  # resolves to cli-abc-company
    body = api_client.get("/health/deep").json()
    assert body["status"] == "healthy"
    assert body["checks"]["client_scope_integrity"] == "ok"


def test_health_deep_flags_orphan_client_ref(api_client, db):
    _add_scope(db, client_ref="cli-does-not-exist")
    body = api_client.get("/health/deep").json()
    assert body["status"] == "degraded"
    assert body["checks"]["client_scope_integrity"] == {"orphan_client_refs": ["cli-does-not-exist"]}
