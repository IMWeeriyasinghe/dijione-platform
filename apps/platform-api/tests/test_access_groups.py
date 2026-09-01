"""Phase 2.6 Access Groups — additive group-based access on top of direct
``UserModuleRole`` assignment (see docs/platform/access-groups.md,
CLAUDE.md-adjacent plan bubbly-bubbling-sifakis.md).

Covers: membership CRUD, group module-assignment CRUD, effective-permission
inheritance (direct-only / group-only / direct+group union), effective
client-scope inheritance (ALL_CLIENTS override + union rule), inactive
groups and disabled group-assignments contributing nothing, unauthorized
group administration, application_detail, audit logging, tenant isolation,
and JWT claims carrying group-derived module_roles.
"""

from app.core.constants import MODULE_TALENT_FLOW
from app.core.security import get_auth_provider
from app.models.access_group import AccessGroup, AccessGroupStatus, GroupModuleRole, UserGroupMembership
from app.services.authorization_service import AuthorizationService
from tests.conftest import ABC_CLIENT_ID, NOVA_CLIENT_ID, XYZ_CLIENT_ID, auth_headers


def _make_group(db, *, key="ta-team", display_name="TA Team", status=AccessGroupStatus.ACTIVE, group_type="TEAM"):
    group = AccessGroup(key=key, display_name=display_name, description="", status=status, group_type=group_type)
    db.add(group)
    db.commit()
    return group


def _add_member(db, group, user):
    db.add(UserGroupMembership(user_id=user.id, access_group_id=group.id))
    db.commit()


def _add_group_role(db, group, *, role, enabled=True, module_key=MODULE_TALENT_FLOW):
    gr = GroupModuleRole(access_group_id=group.id, module_key=module_key, role=role, enabled=enabled)
    db.add(gr)
    db.commit()
    return gr


# --- Route-level CRUD --------------------------------------------------------


def test_group_create_and_list_via_api(api_client, db, two_tenant_world):
    headers = auth_headers(api_client, "test-platform-admin")
    resp = api_client.post(
        "/api/platform/admin/groups",
        json={"key": "ta-team", "display_name": "TA Team", "description": "TA staff", "group_type": "TEAM"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["key"] == "ta-team"
    assert body["members"] == []
    assert body["module_assignments"] == []

    resp = api_client.get("/api/platform/admin/groups", headers=headers)
    assert resp.status_code == 200
    assert any(g["key"] == "ta-team" for g in resp.json())


def test_group_membership_add_remove(api_client, db, two_tenant_world):
    headers = auth_headers(api_client, "test-platform-admin")
    group = _make_group(db)
    ta_user = two_tenant_world["ta_user"]

    resp = api_client.post(
        f"/api/platform/admin/groups/{group.id}/members", json={"user_id": ta_user.id}, headers=headers
    )
    assert resp.status_code == 200
    assert any(m["user_id"] == ta_user.id for m in resp.json()["members"])

    resp = api_client.delete(f"/api/platform/admin/groups/{group.id}/members/{ta_user.id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["members"] == []


def test_group_module_assignment_crud(api_client, db, two_tenant_world):
    headers = auth_headers(api_client, "test-platform-admin")
    group = _make_group(db)

    resp = api_client.put(
        f"/api/platform/admin/groups/{group.id}/modules/{MODULE_TALENT_FLOW}",
        json={"role": "TA_MEMBER", "enabled": True, "client_scope": {"all_clients": True, "client_ids": []}},
        headers=headers,
    )
    assert resp.status_code == 200
    assignment = resp.json()["module_assignments"][0]
    assert assignment["role"] == "TA_MEMBER"
    assert assignment["client_scope"]["all_clients"] is True

    resp = api_client.delete(
        f"/api/platform/admin/groups/{group.id}/modules/{MODULE_TALENT_FLOW}", headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["module_assignments"] == []


def test_unauthorized_group_administration_returns_403(api_client, db, two_tenant_world):
    headers = auth_headers(api_client, "test-abc-client")
    resp = api_client.post(
        "/api/platform/admin/groups", json={"key": "x", "display_name": "X"}, headers=headers
    )
    assert resp.status_code == 403

    resp = api_client.get("/api/platform/admin/groups", headers=headers)
    assert resp.status_code == 403


def test_system_group_cannot_be_deactivated(api_client, db, two_tenant_world):
    headers = auth_headers(api_client, "test-super-admin")
    group = _make_group(db, key="sys", display_name="System Group", group_type="SYSTEM")

    resp = api_client.patch(
        f"/api/platform/admin/groups/{group.id}/status", json={"status": "INACTIVE"}, headers=headers
    )
    assert resp.status_code == 403


def test_group_mutations_are_audited(api_client, db, two_tenant_world):
    headers = auth_headers(api_client, "test-platform-admin")
    resp = api_client.post(
        "/api/platform/admin/groups", json={"key": "audited", "display_name": "Audited"}, headers=headers
    )
    group_id = resp.json()["id"]
    ta_user = two_tenant_world["ta_user"]
    api_client.post(f"/api/platform/admin/groups/{group_id}/members", json={"user_id": ta_user.id}, headers=headers)
    api_client.put(
        f"/api/platform/admin/groups/{group_id}/modules/{MODULE_TALENT_FLOW}",
        json={"role": "TA_MEMBER", "enabled": True, "client_scope": None},
        headers=headers,
    )

    resp = api_client.get(
        "/api/platform/admin/audit", headers=auth_headers(api_client, "test-super-admin")
    )
    actions = {e["action"] for e in resp.json()}
    assert "access_group.created" in actions
    assert "access_group.member_added" in actions
    assert "group_module_assignment.upserted" in actions


# --- Effective permission / client-scope inheritance -----------------------


def test_effective_permissions_direct_only(db, two_tenant_world):
    authz = AuthorizationService(db)
    ta_user = two_tenant_world["ta_user"]
    perms = authz.effective_permissions(ta_user, MODULE_TALENT_FLOW)
    assert "talent.candidates.read" in perms


def test_effective_permissions_group_only(db, two_tenant_world):
    # two_tenant_world["abc_user"] has a direct TALENT_CLIENT role, so use a fresh user instead.
    from app.models.user import User

    fresh = User(email="fresh@example.com", full_name="Fresh User", platform_role="PLATFORM_USER", persona_key="fresh")
    db.add(fresh)
    db.commit()

    group = _make_group(db)
    _add_member(db, group, fresh)
    _add_group_role(db, group, role="TA_MEMBER")

    authz = AuthorizationService(db)
    perms = authz.effective_permissions(fresh, MODULE_TALENT_FLOW)
    assert "talent.candidates.read" in perms


def test_effective_permissions_direct_and_group_union(db, two_tenant_world):
    ta_user = two_tenant_world["ta_user"]  # direct TA_MEMBER
    group = _make_group(db)
    _add_member(db, group, ta_user)
    _add_group_role(db, group, role="CUSTOMER_SUCCESS")

    authz = AuthorizationService(db)
    perms = authz.effective_permissions(ta_user, MODULE_TALENT_FLOW)
    # union includes CUSTOMER_SUCCESS-only permission
    assert "talent.requests.review" in perms
    assert "talent.candidates.read" in perms  # still has TA_MEMBER perms too


def test_effective_access_api_always_includes_sources(api_client, db, two_tenant_world):
    """Regression for the admin-web User Detail crash (`m.sources.map` on
    undefined): the ``EffectiveAccessOut.modules[].sources`` field is
    mandatory in the schema and must be populated for every module entry,
    whether the grant is direct, group-derived, or both, so the frontend
    never receives a module without a `sources` array."""
    ta_user = two_tenant_world["ta_user"]  # has a direct UserModuleRole
    group = _make_group(db, key="cs-team", display_name="CS Team")
    _add_member(db, group, ta_user)
    _add_group_role(db, group, role="CUSTOMER_SUCCESS")

    headers = auth_headers(api_client, "test-platform-admin")
    resp = api_client.get(f"/api/platform/admin/users/{ta_user.id}/effective-access", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    talent_module = next(m for m in body["modules"] if m["module_key"] == MODULE_TALENT_FLOW)
    assert "sources" in talent_module
    assert isinstance(talent_module["sources"], list)
    assert len(talent_module["sources"]) >= 2  # one DIRECT + one GROUP grant
    types = {s["type"] for s in talent_module["sources"]}
    assert types == {"DIRECT", "GROUP"}


def test_inactive_group_contributes_nothing(db, two_tenant_world):
    from app.models.user import User

    fresh = User(email="fresh2@example.com", full_name="Fresh2", platform_role="PLATFORM_USER", persona_key="fresh2")
    db.add(fresh)
    db.commit()

    group = _make_group(db, key="inactive-group", status=AccessGroupStatus.INACTIVE)
    _add_member(db, group, fresh)
    _add_group_role(db, group, role="TA_MEMBER")

    authz = AuthorizationService(db)
    grants = authz.effective_module_roles(fresh)
    assert MODULE_TALENT_FLOW not in grants


def test_disabled_group_assignment_contributes_nothing(db, two_tenant_world):
    from app.models.user import User

    fresh = User(email="fresh3@example.com", full_name="Fresh3", platform_role="PLATFORM_USER", persona_key="fresh3")
    db.add(fresh)
    db.commit()

    group = _make_group(db, key="disabled-assignment-group")
    _add_member(db, group, fresh)
    _add_group_role(db, group, role="TA_MEMBER", enabled=False)

    authz = AuthorizationService(db)
    grants = authz.effective_module_roles(fresh)
    assert MODULE_TALENT_FLOW not in grants


def test_effective_client_scope_all_clients_override(db, two_tenant_world):
    from sqlalchemy import select

    from app.models.user import UserModuleRole
    from tests.conftest import assign_client_scope

    ta_user = two_tenant_world["ta_user"]
    ta_role = db.execute(
        select(UserModuleRole).where(UserModuleRole.user_id == ta_user.id)
    ).scalars().first()
    assign_client_scope(db, ta_role, client_id=ABC_CLIENT_ID)

    group = _make_group(db)
    _add_member(db, group, ta_user)
    gr = _add_group_role(db, group, role="TA_MEMBER")
    from app.models.access_group import GroupModuleClientScope
    db.add(GroupModuleClientScope(group_module_role_id=gr.id, all_clients=True))
    db.commit()

    authz = AuthorizationService(db)
    client_ids, _sources = authz.effective_client_scope(ta_user, MODULE_TALENT_FLOW)
    assert client_ids is None  # ALL_CLIENTS wins even though direct scope was restricted


def test_effective_client_scope_union_rule(db, two_tenant_world):
    from sqlalchemy import select

    from app.models.user import UserModuleRole
    from tests.conftest import assign_client_scope

    ta_user = two_tenant_world["ta_user"]
    ta_role = db.execute(
        select(UserModuleRole).where(UserModuleRole.user_id == ta_user.id)
    ).scalars().first()
    assign_client_scope(db, ta_role, client_id=ABC_CLIENT_ID)

    group = _make_group(db)
    _add_member(db, group, ta_user)
    gr = _add_group_role(db, group, role="TA_MEMBER")
    from app.models.access_group import GroupModuleClientScope
    db.add(GroupModuleClientScope(group_module_role_id=gr.id, client_id=XYZ_CLIENT_ID, all_clients=False))
    db.commit()

    authz = AuthorizationService(db)
    client_ids, _sources = authz.effective_client_scope(ta_user, MODULE_TALENT_FLOW)
    assert set(client_ids) == {ABC_CLIENT_ID, XYZ_CLIENT_ID}


def test_tenant_isolation_preserved_via_group_path(db, two_tenant_world):
    """A group granting TALENT_CLIENT-like scope to ABC only must never leak
    NOVA/XYZ visibility — union rule only ever adds ids explicitly scoped."""
    from sqlalchemy import select

    from app.models.user import UserModuleRole
    from tests.conftest import assign_client_scope

    ta_user = two_tenant_world["ta_user"]
    ta_role = db.execute(
        select(UserModuleRole).where(UserModuleRole.user_id == ta_user.id)
    ).scalars().first()
    assign_client_scope(db, ta_role, client_id=ABC_CLIENT_ID)

    group = _make_group(db)
    _add_member(db, group, ta_user)
    gr = _add_group_role(db, group, role="TA_MEMBER")
    from app.models.access_group import GroupModuleClientScope
    db.add(GroupModuleClientScope(group_module_role_id=gr.id, client_id=XYZ_CLIENT_ID, all_clients=False))
    db.commit()

    authz = AuthorizationService(db)
    client_ids, _sources = authz.effective_client_scope(ta_user, MODULE_TALENT_FLOW)
    assert NOVA_CLIENT_ID not in client_ids


# --- application_detail ------------------------------------------------------


def test_application_detail_endpoint(api_client, db, two_tenant_world):
    from app.models.module import ApplicationModule

    db.add(
        ApplicationModule(
            key=MODULE_TALENT_FLOW, name="DijiTalentFlow", description="d", icon="Users",
            route="/talent-flow", status="ACTIVE", enabled=True, display_order=1, required_roles="ANY",
        )
    )
    db.commit()

    group = _make_group(db)
    _add_member(db, group, two_tenant_world["cs_user"])
    _add_group_role(db, group, role="CUSTOMER_SUCCESS")

    headers = auth_headers(api_client, "test-platform-admin")
    resp = api_client.get(f"/api/platform/admin/applications/{MODULE_TALENT_FLOW}", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["module_key"] == MODULE_TALENT_FLOW
    assert body["direct_user_count"] >= 1
    assert body["group_count"] == 1
    assert body["assigned_groups"][0]["group_key"] == group.key


# --- JWT claims --------------------------------------------------------------


def test_jwt_claims_include_group_derived_module_roles(api_client, db, two_tenant_world):
    from app.models.user import User

    fresh = User(email="fresh4@example.com", full_name="Fresh4", platform_role="PLATFORM_USER", persona_key="fresh4")
    db.add(fresh)
    db.commit()

    group = _make_group(db)
    _add_member(db, group, fresh)
    _add_group_role(db, group, role="TA_MEMBER")

    resp = api_client.post("/api/auth/dev-login", json={"persona_key": "fresh4"})
    assert resp.status_code == 200
    claims = get_auth_provider().decode_token(resp.json()["access_token"])
    assert claims["module_roles"][MODULE_TALENT_FLOW]["role"] == "TA_MEMBER"
    assert "talent.candidates.read" in claims["module_roles"][MODULE_TALENT_FLOW]["permissions"]
