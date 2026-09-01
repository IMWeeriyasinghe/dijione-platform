"""Client-scope integrity is now a purely local check against the
platform-owned ``clients`` table (Architecture Completion Plan §6.1) — no
cross-service HTTP call. A concrete client id in a module/group scope must
resolve to a canonical ``Client`` (directly by ``Client.id`` or via the
``talent-api`` legacy crosswalk); an unknown id -> 400.
"""

from tests.conftest import ABC_CLIENT_ID, auth_headers

MODULE = "talent-flow"


def _put_scope(api_client, headers, user_id, client_ids):
    return api_client.put(
        f"/api/platform/admin/users/{user_id}/modules/{MODULE}",
        headers=headers,
        json={
            "role": "TA_MEMBER",
            "enabled": True,
            "client_scope": {"all_clients": False, "client_ids": client_ids},
        },
    )


def test_known_client_id_is_accepted(api_client, two_tenant_world):
    headers = auth_headers(api_client, "test-super-admin")
    resp = _put_scope(api_client, headers, two_tenant_world["ta_user"].id, [ABC_CLIENT_ID])
    assert resp.status_code == 200, resp.text


def test_unknown_client_id_is_rejected_400(api_client, two_tenant_world):
    headers = auth_headers(api_client, "test-super-admin")
    resp = _put_scope(api_client, headers, two_tenant_world["ta_user"].id, [ABC_CLIENT_ID, 999])
    assert resp.status_code == 400
    assert "999" in resp.text


def test_all_clients_scope_skips_client_resolution(api_client, two_tenant_world):
    headers = auth_headers(api_client, "test-super-admin")
    resp = api_client.put(
        f"/api/platform/admin/users/{two_tenant_world['ta_user'].id}/modules/{MODULE}",
        headers=headers,
        json={"role": "TA_MEMBER", "enabled": True, "client_scope": {"all_clients": True, "client_ids": []}},
    )
    assert resp.status_code == 200, resp.text


def test_scope_row_carries_client_ref(api_client, two_tenant_world):
    """The persisted scope row stores the durable ``client_ref`` public id,
    not just the legacy integer."""
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.user import UserModuleRole
    from app.models.user_module_client_scope import UserModuleClientScope

    headers = auth_headers(api_client, "test-super-admin")
    ta_id = two_tenant_world["ta_user"].id
    assert _put_scope(api_client, headers, ta_id, [ABC_CLIENT_ID]).status_code == 200

    with SessionLocal() as s:
        mr = s.execute(
            select(UserModuleRole).where(
                UserModuleRole.user_id == ta_id, UserModuleRole.module_key == MODULE
            )
        ).scalars().one()
        scope = s.execute(
            select(UserModuleClientScope).where(
                UserModuleClientScope.user_module_role_id == mr.id
            )
        ).scalars().one()
        assert scope.client_ref == "cli-abc-company"
