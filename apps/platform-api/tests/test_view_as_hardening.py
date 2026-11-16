"""View-as: findings from the independent review."""

import pytest
from sqlalchemy import select

from app.core.security import issue_session_token
from app.models.audit_log import AuditLog
from app.models.user import User
from tests.conftest import auth_headers, make_eligible

START = "/api/platform/admin/view-as"


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("VIEW_AS_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def world(db, two_tenant_world):
    make_eligible(db.get(User, two_tenant_world["ta_user"].id))
    db.commit()
    return two_tenant_world


def test_a_staff_marked_token_that_carries_a_view_as_claim_is_not_a_staff_session(api_client, world):
    admin = world["super_admin"]
    forged = issue_session_token(
        admin.id, email=admin.email, is_active=True, full_name="x", platform_role="SUPER_ADMIN",
        platform_permissions=[], module_roles={}, av=0,
        view_as={"session_id": "S", "actor_id": admin.id, "actor_name": "x", "actor_av": 0},
    )
    resp = api_client.get("/api/platform/admin/users", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 401


def test_replacing_a_session_is_audited_as_an_end(db, world, api_client):
    headers = auth_headers(api_client, "test-super-admin")
    for _ in range(2):
        assert api_client.post(START, json={"target_user_id": world["ta_user"].id}, headers=headers).status_code == 201
    reasons = [
        a.new_state for a in db.execute(select(AuditLog).where(AuditLog.action == "view_as.ended")).scalars()
    ]
    assert len(reasons) == 1 and '"replaced"' in reasons[0]
