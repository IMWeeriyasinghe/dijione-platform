"""Phase 2.5 CR §19-20: the token issued at login carries signed
authorization claims so downstream services (talent-api, birthday-api,
spark-api) can authorize requests locally, without calling Platform Core.
"""

from app.core.security import get_auth_provider
from tests.conftest import ABC_CLIENT_ID, XYZ_CLIENT_ID, assign_client_scope


def _decode(token: str) -> dict:
    return get_auth_provider().decode_token(token)


def test_dev_login_embeds_module_role_claims(api_client, db, two_tenant_world):
    resp = api_client.post("/api/auth/dev-login", json={"persona_key": "test-cs"})
    assert resp.status_code == 200
    claims = _decode(resp.json()["access_token"])

    assert claims["is_active"] is True
    assert "platform_permissions" in claims
    talent_claim = claims["module_roles"]["talent-flow"]
    assert talent_claim["role"] == "CUSTOMER_SUCCESS"
    assert "talent.requests.review" in talent_claim["permissions"]
    assert talent_claim["client_ids"] is None  # ALL_CLIENTS (no scope rows seeded)


def test_dev_login_embeds_client_scope_claims(api_client, db, two_tenant_world):
    from sqlalchemy import select

    from app.models.user import UserModuleRole

    ta_role = db.execute(
        select(UserModuleRole).where(UserModuleRole.user_id == two_tenant_world["ta_user"].id)
    ).scalars().first()
    assign_client_scope(db, ta_role, client_id=ABC_CLIENT_ID)
    assign_client_scope(db, ta_role, client_id=XYZ_CLIENT_ID)

    resp = api_client.post("/api/auth/dev-login", json={"persona_key": "test-ta"})
    claims = _decode(resp.json()["access_token"])
    assert set(claims["module_roles"]["talent-flow"]["client_ids"]) == {ABC_CLIENT_ID, XYZ_CLIENT_ID}


def test_disabled_module_assignment_excluded_from_claims(api_client, db, two_tenant_world):
    from sqlalchemy import select

    from app.models.user import UserModuleRole

    ta_role = db.execute(
        select(UserModuleRole).where(UserModuleRole.user_id == two_tenant_world["ta_user"].id)
    ).scalars().first()
    ta_role.enabled = False
    db.commit()

    resp = api_client.post("/api/auth/dev-login", json={"persona_key": "test-ta"})
    claims = _decode(resp.json()["access_token"])
    assert "talent-flow" not in claims["module_roles"]


def test_disabled_user_cannot_login(api_client, db, two_tenant_world):
    two_tenant_world["ta_user"].is_active = False
    db.commit()

    resp = api_client.post("/api/auth/dev-login", json={"persona_key": "test-ta"})
    assert resp.status_code == 403
