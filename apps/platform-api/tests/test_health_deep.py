"""/health/deep readiness probe: DB, migration revision, auth mode, and the
temporary client-scope integrity check."""

import httpx

from app.core.constants import MODULE_TALENT_FLOW
from app.models.user import User, UserModuleRole
from app.services import client_directory
from tests.conftest import ABC_CLIENT_ID, XYZ_CLIENT_ID, assign_client_scope


def _add_scope(db, client_id: int) -> None:
    user = User(
        email=f"u{client_id}@example.com", full_name="U", platform_role="PLATFORM_USER",
        persona_key=f"x{client_id}",
    )
    db.add(user)
    db.flush()
    mr = UserModuleRole(user_id=user.id, module_key=MODULE_TALENT_FLOW, role="TA_MEMBER")
    db.add(mr)
    db.flush()
    assign_client_scope(db, mr, client_id=client_id)


def test_health_deep_ok(api_client, db):
    resp = api_client.get("/health/deep")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["auth_mode"] == "dev"
    assert body["checks"]["client_scope_integrity"] == "ok"  # no scope rows yet


def test_health_deep_flags_orphan_client_scope(api_client, db, monkeypatch):
    _add_scope(db, 999)  # not a real talent-api client
    monkeypatch.setattr(client_directory, "known_client_ids", lambda: {ABC_CLIENT_ID, XYZ_CLIENT_ID})

    body = api_client.get("/health/deep").json()
    assert body["status"] == "degraded"
    assert body["checks"]["client_scope_integrity"] == {"orphan_client_ids": [999]}


def test_health_deep_tolerates_talent_api_down(api_client, db, monkeypatch):
    _add_scope(db, ABC_CLIENT_ID)

    def _down():
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(client_directory, "known_client_ids", _down)
    body = api_client.get("/health/deep").json()
    # talent-api being unreachable is diagnostic only — readiness stays healthy.
    assert body["status"] == "healthy"
    assert body["checks"]["client_scope_integrity"] == "unavailable"
