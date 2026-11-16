"""Effective Access Diagnostics: read-only, explains access from recorded facts."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.access_group import AccessGroup, GroupModuleRole, UserGroupMembership
from app.models.audit_log import AuditLog
from app.models.module import ApplicationModule
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
    assert [m["has_access"] for m in data["modules"]] == [False]
    assert data["modules"][0]["inactive"][0]["reason"].startswith("The group is inactive")
    assert any(c["key"] == "no_access" for c in data["checks"])
    assert data["groups"][0]["status"] == "INACTIVE"


def test_disabled_direct_assignment_listed_as_inactive(api_client, db, two_tenant_world):
    admin = auth_headers(api_client, "test-platform-admin")
    ta_id = two_tenant_world["ta_user"].id
    api_client.put(
        f"/api/platform/admin/users/{ta_id}/modules/{MODULE}", json={"role": "TA_MEMBER", "enabled": False}, headers=admin
    )
    data = _diag(api_client, ta_id)
    assert [m["has_access"] for m in data["modules"]] == [False]
    assert data["modules"][0]["inactive"][0]["type"] == "DIRECT"
    assert any(c["key"] == "no_access" for c in data["checks"])


def test_default_access_states(api_client, db, two_tenant_world):
    from app.models.module_baseline import ModuleBaselineRole
    db.add(ApplicationModule(key="field-ops", name="Field Ops", description="", route="/field-ops",
                             required_roles="ANY", supports_client_scope=False))
    db.add(ModuleBaselineRole(module_key="field-ops", role="FIELD_USER", enabled=True))
    db.commit()
    user = two_tenant_world["ta_user"]
    data = _diag(api_client, user.id)
    state = next(d for d in data["default_access"] if d["module_key"] == "field-ops")
    assert state["state"] == "NOT_ELIGIBLE"
    assert any("Microsoft" in r for r in state["reasons"])

    u = db.get(User, user.id)
    u.identity_provider, u.entra_object_id, u.internal_employee = "ENTRA", "oid-1", True
    u.employee_record_status = "MATCHED"
    db.commit()
    state = next(d for d in _diag(api_client, user.id)["default_access"] if d["module_key"] == "field-ops")
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


# --- correction: parity with the resolver, and visibility without access ---------


def _claim(db, user_id, module=MODULE):
    from app.services.claims_service import build_claims

    return build_claims(db.get(User, user_id), db)["module_roles"][module]


def test_mixed_direct_and_group_grants_match_the_token_exactly(api_client, db, two_tenant_world):
    user = User(email="mix@example.com", full_name="Mix", persona_key="test-mix")
    group = AccessGroup(key="cs", display_name="CS Group")
    db.add_all([user, group])
    db.flush()
    direct = UserModuleRole(user_id=user.id, module_key=MODULE, role="TA_MEMBER")
    db.add(direct)
    db.flush()
    assign_client_scope(db, direct, client_id=ABC_CLIENT_ID)
    grant = GroupModuleRole(access_group_id=group.id, module_key=MODULE, role="CUSTOMER_SUCCESS")
    db.add_all([UserGroupMembership(user_id=user.id, access_group_id=group.id), grant])
    db.commit()

    claim = _claim(db, user.id)
    module = next(m for m in _diag(api_client, user.id)["modules"] if m["module_key"] == MODULE)
    assert module["role"] == claim["role"]
    assert module["permissions"] == claim["permissions"]
    assert module["client_scope"]["all_clients"] is (claim["client_ids"] is None)
    assert sorted(s["type"] for s in module["sources"]) == ["DIRECT", "GROUP"]
    union = set()
    for s in module["sources"]:
        union |= set(s["permissions"])
    assert sorted(union) == claim["permissions"]
    # Group has no scope rows, so the union is unrestricted, as in the token.
    assert module["client_scope"]["all_clients"] is True


def test_inactive_account_keeps_grants_visible_but_applies_nothing(api_client, db, two_tenant_world):
    user = db.get(User, two_tenant_world["ta_user"].id)
    user.is_active = False
    db.commit()
    data = _diag(api_client, user.id)
    module = next(m for m in data["modules"] if m["module_key"] == MODULE)
    assert module["has_access"] is False
    assert module["sources"]  # still explained
    assert any(c["key"] == "account_inactive" for c in data["checks"])


def test_no_effective_access_still_shows_why(api_client, db, two_tenant_world):
    from app.models.module_baseline import ModuleBaselineRole
    db.add(ApplicationModule(key="field-ops", name="Field Ops", description="", route="/field-ops",
                             required_roles="ANY", supports_client_scope=False))
    db.add(ModuleBaselineRole(module_key="field-ops", role="FIELD_USER", enabled=True))
    # Identity verified, but not matched to an employee record: no default access (a service account).
    user = User(email="none@example.com", full_name="None", persona_key="test-none", internal_employee=True,
                identity_provider="ENTRA", entra_object_id="oid-none", employee_record_status="NOT_FOUND")
    group = AccessGroup(key="off", display_name="Off Group", status="INACTIVE")
    db.add_all([user, group])
    db.flush()
    db.add_all([
        UserModuleRole(user_id=user.id, module_key=MODULE, role="TA_MEMBER", enabled=False),  # disabled direct
        UserGroupMembership(user_id=user.id, access_group_id=group.id),
        GroupModuleRole(access_group_id=group.id, module_key="spark", role="SPARK_USER"),
    ])
    db.commit()

    data = _diag(api_client, user.id)
    by_key = {m["module_key"]: m for m in data["modules"]}
    assert {m["has_access"] for m in data["modules"]} == {False}
    assert by_key[MODULE]["inactive"][0]["type"] == "DIRECT"
    default = next(d for d in data["default_access"] if d["module_key"] == "field-ops")
    assert default["state"] == "NOT_ELIGIBLE" and any("employee record" in r for r in default["reasons"])
    assert by_key["spark"]["inactive"][0]["group_name"] == "Off Group"
    assert "No access" in by_key[MODULE]["scope_explanation"]
    assert any(c["key"] == "no_access" for c in data["checks"])
