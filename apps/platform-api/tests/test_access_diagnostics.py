"""Effective Access Diagnostics: read-only, explains access from recorded facts."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.access_group import AccessGroup, GroupModuleRole, UserGroupMembership
from app.models.audit_log import AuditLog
from app.models.user import User, UserModuleRole
from tests.conftest import ABC_CLIENT_ID, assign_client_scope, auth_headers

MODULE = "talent-flow"


def _diag(api_client, user_id, headers=None):
    headers = headers or auth_headers(api_client, "test-platform-admin")
    resp = api_client.get(f"/api/platform/admin/users/{user_id}/access-diagnostics", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_requires_platform_admin(api_client, db, two_tenant_world):
    uid = two_tenant_world["ta_user"].id
    url = f"/api/platform/admin/users/{uid}/access-diagnostics"
    assert api_client.get(url).status_code in (401, 403)
    assert api_client.get(url, headers=auth_headers(api_client, "test-ta")).status_code == 403


def test_unknown_user_is_404(api_client, db, two_tenant_world):
    resp = api_client.get(
        "/api/platform/admin/users/99999/access-diagnostics", headers=auth_headers(api_client, "test-platform-admin")
    )
    assert resp.status_code == 404


def test_direct_role_sources_permissions_and_scope(api_client, db, two_tenant_world):
    role = db.execute(
        select(UserModuleRole).where(UserModuleRole.user_id == two_tenant_world["abc_user"].id)
    ).scalars().one()
    assign_client_scope(db, role, client_id=ABC_CLIENT_ID)
    data = _diag(api_client, two_tenant_world["abc_user"].id)

    module = next(m for m in data["modules"] if m["module_key"] == MODULE)
    assert module["role"] == "TALENT_CLIENT"
    assert [s["type"] for s in module["sources"]] == ["DIRECT"]
    assert module["sources"][0]["permissions"] == module["permissions"]
    assert module["client_scope"]["all_clients"] is False
    assert module["client_scope"]["client_ids"] == [ABC_CLIENT_ID]
    assert "Restricted" in module["scope_explanation"]
    assert data["account"]["is_active"] is True


def test_group_inheritance_and_inactive_group_is_explained(api_client, db, two_tenant_world):
    user = User(email="grp@example.com", full_name="Grp User", persona_key="test-grp")
    group = AccessGroup(key="ta-team", display_name="TA Team")
    db.add_all([user, group])
    db.flush()
    db.add_all([
        UserGroupMembership(user_id=user.id, access_group_id=group.id),
        GroupModuleRole(access_group_id=group.id, module_key=MODULE, role="TA_MEMBER"),
    ])
    db.commit()

    data = _diag(api_client, user.id)
    module = next(m for m in data["modules"] if m["module_key"] == MODULE)
    assert [(s["type"], s["group_name"], s["role"]) for s in module["sources"]] == [("GROUP", "TA Team", "TA_MEMBER")]
    assert data["groups"][0]["group_name"] == "TA Team"
    assert data["groups"][0]["grants"][0]["role"] == "TA_MEMBER"

    group.status = "INACTIVE"
    db.commit()
    data = _diag(api_client, user.id)
    assert data["modules"] == []
    assert any(c["key"] == "no_access" for c in data["checks"])
    assert data["groups"][0]["status"] == "INACTIVE"


def test_disabled_direct_assignment_listed_as_inactive(api_client, db, two_tenant_world):
    admin = auth_headers(api_client, "test-platform-admin")
    ta_id = two_tenant_world["ta_user"].id
    api_client.put(
        f"/api/platform/admin/users/{ta_id}/modules/{MODULE}", json={"role": "TA_MEMBER", "enabled": False}, headers=admin
    )
    data = _diag(api_client, ta_id)
    assert data["modules"] == []
    assert any(c["key"] == "no_access" for c in data["checks"])


def test_default_access_states(api_client, db, two_tenant_world):
    from app.models.module_baseline import ModuleBaselineRole
    from tests.test_atwork_registration import _register_module

    _register_module(db)
    db.add(ModuleBaselineRole(module_key="atwork", role="ATWORK_USER", enabled=True))
    db.commit()
    user = two_tenant_world["ta_user"]
    data = _diag(api_client, user.id)
    state = next(d for d in data["default_access"] if d["module_key"] == "atwork")
    assert state["state"] == "NOT_ELIGIBLE"
    assert any("Microsoft" in r for r in state["reasons"])

    u = db.get(User, user.id)
    u.identity_provider, u.entra_object_id, u.internal_employee = "ENTRA", "oid-1", True
    db.commit()
    state = next(d for d in _diag(api_client, user.id)["default_access"] if d["module_key"] == "atwork")
    assert state["state"] == "GRANTED"


def test_token_freshness_is_reported_unavailable(api_client, db, two_tenant_world):
    data = _diag(api_client, two_tenant_world["ta_user"].id)
    assert data["session"]["token_issue_time_available"] is False
    assert "Not recorded" in data["session"]["token_issue_time_note"]
    assert data["session"]["token_lifetime_minutes"] == 720


def test_changes_after_last_sign_in_are_counted_from_the_audit_log(api_client, db, two_tenant_world):
    user = db.get(User, two_tenant_world["ta_user"].id)
    signed_in = datetime.now(UTC) - timedelta(hours=2)
    user.last_login_at = signed_in
    db.add(AuditLog(
        actor_id=None, action="user.module_assigned", entity_type="user", entity_id=user.id,
        previous_state="", new_state="", event_metadata="", subject_user_id=user.id,
        created_at=signed_in + timedelta(minutes=30),
    ))
    db.add(AuditLog(
        actor_id=None, action="user.module_assigned", entity_type="user", entity_id=user.id,
        previous_state="", new_state="", event_metadata="", subject_user_id=user.id,
        created_at=signed_in - timedelta(minutes=30),
    ))
    db.commit()
    session = _diag(api_client, user.id)["session"]
    assert session["access_changes_since_last_sign_in"] == 1
    assert session["latest_access_change_at"] is not None


def test_never_signed_in_has_no_change_count(api_client, db, two_tenant_world):
    user = db.get(User, two_tenant_world["ta_user"].id)
    user.last_login_at = None
    db.commit()
    data = _diag(api_client, user.id)
    assert data["session"]["access_changes_since_last_sign_in"] is None
    assert any(c["key"] == "never_signed_in" for c in data["checks"])


def test_diagnostics_never_writes(api_client, db, two_tenant_world):
    before = db.execute(select(AuditLog)).scalars().all()
    _diag(api_client, two_tenant_world["ta_user"].id)
    db.expire_all()
    assert len(db.execute(select(AuditLog)).scalars().all()) == len(before)
