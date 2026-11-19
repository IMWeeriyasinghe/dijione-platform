"""Delegated application access administration: appointment, authority, grants, revocation with
application suspension, directory onboarding, precedence, consistency with Central Admin, and the
negative cases (self, other administrators, cross-application, outside authority, View-as)."""

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.integrations.directory import DirectoryUser, MockDirectoryProvider, set_directory_provider
from app.integrations.people import EmployeeRecord, EmployeeRecordChecker, set_employee_record_checker
from app.models.access_group import AccessGroup, GroupModuleClientScope, GroupModuleRole, UserGroupMembership
from app.models.application_access import ApplicationAccessSuspension, ApplicationAdministrator
from app.models.audit_log import AuditLog
from app.models.module import ApplicationModule
from app.models.module_baseline import ModuleBaselineRole
from app.models.user import User, UserModuleRole
from app.services.authorization_service import AuthorizationService
from app.services.claims_service import build_claims
from app.services.delegated_access_rollback import check as rollback_check
from tests.conftest import auth_headers, internal_headers, make_eligible

TALENT, BIRTHDAY = "talent-flow", "birthday"
ADMIN = "/api/platform/admin"
ABC, XYZ = 1, 2  # platform Client.id (seeded in this order by conftest)
OID_NEW = "11111111-0000-4000-8000-000000000001"
OID_NOHR = "11111111-0000-4000-8000-000000000002"


def _person(oid, name, email):
    return DirectoryUser(object_id=oid, display_name=name, email=email, user_principal_name=email,
                         job_title="Recruiter", department="TA", account_enabled=True, user_type="Member")


class _Records(EmployeeRecordChecker):
    def __init__(self, statuses):
        self.statuses = statuses

    def check(self, *, email, employee_id=None, cached_only=False, wait_seconds=0.0):
        return EmployeeRecord(self.statuses.get((email or "").lower(), "MATCHED"))


@pytest.fixture(autouse=True)
def _feature(monkeypatch):
    monkeypatch.setenv("DELEGATED_ACCESS_ENABLED", "true")
    monkeypatch.setenv("ENTRA_INTERNAL_EMAIL_DOMAINS", "example.com")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def world(db, two_tenant_world):
    db.add_all([
        ApplicationModule(key=TALENT, name="DijiTalentFlow", description="", route="/talent-flow"),
        ApplicationModule(key=BIRTHDAY, name="DIJI Birthday", description="", route="/birthday",
                          supports_client_scope=False),
    ])
    people = {}
    for key in ("tom", "david", "erin", "gina", "hal"):
        user = User(email=f"{key}@example.com", full_name=key.title(), persona_key=f"test-{key}")
        make_eligible(user)
        db.add(user)
        people[key] = user
    outsider = User(email="outsider@example.com", full_name="Outsider", persona_key="test-outsider")
    db.add(outsider)
    people["outsider"] = outsider
    db.flush()
    # Gina holds a centrally granted TA_MANAGER for all clients (outside Tom's authority).
    gina_role = UserModuleRole(user_id=people["gina"].id, module_key=TALENT, role="TA_MANAGER")
    db.add(gina_role)
    db.commit()
    for name in ("super_admin", "platform_admin"):
        make_eligible(db.get(User, two_tenant_world[name].id))
    db.commit()
    return {**two_tenant_world, **people}


def _h(api_client, persona):
    return auth_headers(api_client, persona)


def _appoint(api_client, module, user_id, roles, clients=None, *, who="test-super-admin", can_appoint=False, **extra):
    body = {"grantable_roles": roles, "can_appoint_admins": can_appoint, **extra}
    if clients is not None:
        body["client_authority"] = {"all_clients": clients == "ALL", "client_ids": [] if clients == "ALL" else clients}
    return api_client.put(f"{ADMIN}/applications/{module}/administrators/{user_id}", json=body, headers=_h(api_client, who))


@pytest.fixture()
def tom(api_client, world):
    resp = _appoint(api_client, TALENT, world["tom"].id, ["TA_MEMBER", "CUSTOMER_SUCCESS"], [ABC])
    assert resp.status_code == 200, resp.text
    return world["tom"]


def _grant(api_client, who, module, user_id, role, clients=None):
    body = {"role": role}
    if clients is not None:
        body["client_scope"] = {"all_clients": clients == "ALL", "client_ids": [] if clients == "ALL" else clients}
    return api_client.put(f"/api/access/{module}/users/{user_id}", json=body, headers=_h(api_client, who))


def _perms(db, user, module):
    db.expire_all()
    return AuthorizationService(db).effective_permissions(db.get(User, user.id), module)


def _av(db, user):
    db.expire_all()
    return db.get(User, user.id).access_version


# --- appointment ---------------------------------------------------------------------------------


def test_only_a_super_admin_appoints_and_only_eligible_employees(api_client, world):
    assert _appoint(api_client, TALENT, world["tom"].id, ["TA_MEMBER"], [ABC], who="test-platform-admin").status_code == 403
    assert _appoint(api_client, TALENT, world["outsider"].id, ["TA_MEMBER"], [ABC]).status_code == 403
    assert _appoint(api_client, TALENT, world["tom"].id, ["TALENT_CLIENT"], [ABC]).status_code == 400  # not delegable
    assert _appoint(api_client, TALENT, world["tom"].id, ["TALENT_ACCESS_ADMIN"], [ABC]).status_code == 400
    assert _appoint(api_client, TALENT, world["tom"].id, ["TA_MEMBER"]).status_code == 400  # scoped app: clients required
    assert _appoint(api_client, "spark", world["tom"].id, ["X"]).status_code == 404  # no delegation for this app
    assert _appoint(api_client, TALENT, world["tom"].id, ["TA_MEMBER"], [ABC]).status_code == 200


def test_appointment_gives_an_admin_only_entry_with_no_business_permission(api_client, db, tom):
    claims = build_claims(db.get(User, tom.id), db)["module_roles"][TALENT]
    assert claims["role"] == "TALENT_ACCESS_ADMIN"
    assert claims["permissions"] == ["talent.access.manage"]
    assert claims["client_public_ids"] == [] and claims["client_ids"] == []  # no client data reachable
    headers = _h(api_client, "test-tom")
    assert TALENT in {m["key"] for m in api_client.get("/api/modules", headers=headers).json()}
    me = api_client.get("/api/auth/me", headers=headers).json()["module_roles"]
    assert {"module_key": TALENT, "permissions": ["talent.access.manage"]}.items() <= next(
        e for e in me if e["module_key"] == TALENT
    ).items()
    access_me = api_client.get(f"/api/access/{TALENT}/me", headers=headers).json()
    assert access_me["is_admin"] and [r["key"] for r in access_me["grantable_roles"]] == ["TA_MEMBER", "CUSTOMER_SUCCESS"]
    assert access_me["client_authority"] == {"all_clients": False, "clients": [{"id": ABC, "name": "ABC Company"}]}


def test_business_role_stays_primary_and_permissions_union(api_client, db, world):
    db.add(UserModuleRole(user_id=world["tom"].id, module_key=TALENT, role="TA_MEMBER"))
    db.commit()
    assert _appoint(api_client, TALENT, world["tom"].id, ["TA_MEMBER"], [ABC]).status_code == 200
    claims = build_claims(db.get(User, world["tom"].id), db)["module_roles"][TALENT]
    assert claims["role"] == "TA_MEMBER"
    assert "talent.access.manage" in claims["permissions"] and "talent.workspace.staff" in claims["permissions"]


def test_appointment_only_roles_cannot_be_assigned_centrally_or_by_group(api_client, db, world):
    headers = _h(api_client, "test-super-admin")
    resp = api_client.put(f"{ADMIN}/users/{world['erin'].id}/modules/{TALENT}",
                          json={"role": "TALENT_ACCESS_ADMIN", "client_scope": {"all_clients": True}}, headers=headers)
    assert resp.status_code == 400
    group = AccessGroup(key="g", display_name="G")
    db.add(group)
    db.commit()
    resp = api_client.put(f"{ADMIN}/groups/{group.id}/modules/{TALENT}",
                          json={"role": "TALENT_ACCESS_OWNER", "client_scope": {"all_clients": True}}, headers=headers)
    assert resp.status_code == 400


def test_an_ineligible_appointee_holds_nothing(api_client, db, tom):
    db.get(User, tom.id).employee_record_status = "NOT_FOUND"
    db.commit()
    assert TALENT not in build_claims(db.get(User, tom.id), db)["module_roles"]
    assert api_client.get(f"/api/access/{TALENT}/users", headers=_h(api_client, "test-tom")).status_code == 403


# --- granting ------------------------------------------------------------------------------------


def test_admin_grants_within_authority_and_it_reaches_the_session(api_client, db, world, tom):
    david = world["david"]
    before = _av(db, david)
    resp = _grant(api_client, "test-tom", TALENT, david.id, "TA_MEMBER", [ABC])
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "TA_MEMBER" and resp.json()["has_access"]
    assert "talent.requests.read" in _perms(db, david, TALENT)
    assert _av(db, david) > before  # David's open sessions are revoked and refresh with the new role
    claims = build_claims(db.get(User, david.id), db)["module_roles"][TALENT]
    assert claims["client_public_ids"] == ["cli-abc-company"]
    entry = db.execute(select(AuditLog).where(AuditLog.action == "module_assignment.created")).scalars().one()
    assert '"channel": "APPLICATION"' in entry.event_metadata and entry.actor_id == tom.id


@pytest.mark.parametrize(
    ("role", "clients", "status"),
    [
        ("TA_MANAGER", [ABC], 403),  # role outside authority
        ("TA_MEMBER", [XYZ], 403),  # client outside authority
        ("TA_MEMBER", "ALL", 403),  # broader than authority
        ("TALENT_CLIENT", [ABC], 403),  # never delegable
        ("TALENT_ACCESS_ADMIN", [ABC], 403),  # administrator-only role
        ("TA_MEMBER", None, 400),  # scoped app needs a scope
    ],
)
def test_grants_outside_authority_are_refused(api_client, db, world, tom, role, clients, status):
    assert _grant(api_client, "test-tom", TALENT, world["david"].id, role, clients).status_code == status
    assert db.execute(select(UserModuleRole).where(UserModuleRole.user_id == world["david"].id)).first() is None


@pytest.mark.parametrize("target", ["tom", "super_admin", "platform_admin", "outsider"])
def test_protected_targets_are_refused(api_client, db, world, tom, target):
    assert _grant(api_client, "test-tom", TALENT, world[target].id, "TA_MEMBER", [ABC]).status_code == 403


def test_another_administrator_of_the_same_app_cannot_be_changed(api_client, world, tom):
    assert _appoint(api_client, TALENT, world["erin"].id, ["TA_MEMBER"], [ABC]).status_code == 200
    assert _grant(api_client, "test-tom", TALENT, world["erin"].id, "TA_MEMBER", [ABC]).status_code == 403
    assert api_client.post(f"/api/access/{TALENT}/users/{world['erin'].id}/revoke", json={},
                           headers=_h(api_client, "test-tom")).status_code == 403


def test_no_authority_in_another_application(api_client, world, tom):
    assert _grant(api_client, "test-tom", BIRTHDAY, world["david"].id, "BIRTHDAY_USER").status_code == 403
    assert api_client.get(f"/api/access/{BIRTHDAY}/users", headers=_h(api_client, "test-tom")).status_code == 403


def test_centrally_granted_access_outside_authority_is_read_only(api_client, db, world, tom):
    gina = world["gina"]
    assert _grant(api_client, "test-tom", TALENT, gina.id, "TA_MEMBER", [ABC]).status_code == 403
    users = api_client.get(f"/api/access/{TALENT}/users", headers=_h(api_client, "test-tom")).json()["users"]
    listed = {u["user_id"]: u for u in users}
    assert listed[gina.id]["manageable"] is False and "Central Admin" in listed[gina.id]["managed_reason"]
    assert api_client.post(f"/api/access/{TALENT}/users/{gina.id}/revoke", json={},
                           headers=_h(api_client, "test-tom")).status_code == 403
    assert db.execute(select(UserModuleRole).where(UserModuleRole.user_id == gina.id)).scalars().one().role == "TA_MANAGER"


def test_non_admins_and_view_as_get_nothing(api_client, db, world, tom, monkeypatch):
    assert api_client.get(f"/api/access/{TALENT}/me", headers=_h(api_client, "test-david")).json()["is_admin"] is False
    assert api_client.get(f"/api/access/{TALENT}/users", headers=_h(api_client, "test-david")).status_code == 403
    monkeypatch.setenv("VIEW_AS_ENABLED", "true")
    get_settings.cache_clear()
    started = api_client.post(f"{ADMIN}/view-as", json={"target_user_id": tom.id}, headers=_h(api_client, "test-super-admin"))
    assert started.status_code == 201, started.text
    view_as = {"Authorization": f"Bearer {started.json()['access_token']}"}
    assert api_client.get("/api/auth/me", headers=view_as).status_code == 200  # the View-as session itself works
    for method, path in [("get", "users"), ("get", "me"), ("put", f"users/{world['david'].id}")]:
        resp = getattr(api_client, method)(f"/api/access/{TALENT}/{path}", headers=view_as,
                                           **({"json": {"role": "TA_MEMBER"}} if method == "put" else {}))
        assert resp.status_code == 403, path  # a View-as session never reaches access administration


def test_feature_switched_off_hides_every_endpoint_but_enforcement_stays(api_client, db, world, tom, monkeypatch):
    assert _grant(api_client, "test-tom", TALENT, world["david"].id, "TA_MEMBER", [ABC]).status_code == 200
    monkeypatch.setenv("DELEGATED_ACCESS_ENABLED", "false")
    get_settings.cache_clear()
    assert api_client.get(f"/api/access/{TALENT}/users", headers=_h(api_client, "test-tom")).status_code == 404
    assert _appoint(api_client, TALENT, world["erin"].id, ["TA_MEMBER"], [ABC]).status_code == 404
    assert "talent.access.manage" in _perms(db, tom, TALENT)  # nothing already granted is silently changed
    assert "talent.requests.read" in _perms(db, world["david"], TALENT)


# --- revocation, suspension, precedence -------------------------------------------------------------


def _group(db, name, user, module, role, *, system=False, clients=None):
    group = AccessGroup(key=name, display_name=name, group_type="SYSTEM" if system else "TEAM")
    db.add(group)
    db.flush()
    db.add(UserGroupMembership(user_id=user.id, access_group_id=group.id))
    grant = GroupModuleRole(access_group_id=group.id, module_key=module, role=role)
    db.add(grant)
    db.flush()
    if clients is not None:
        for cid, ref in clients:
            db.add(GroupModuleClientScope(group_module_role_id=grant.id, client_id=cid, client_ref=ref, all_clients=False))
    db.commit()
    return group


def _revoke(api_client, who, module, user_id, reason="Left the team"):
    return api_client.post(f"/api/access/{module}/users/{user_id}/revoke", json={"reason": reason}, headers=_h(api_client, who))


def test_revoking_only_direct_access_deletes_it_without_a_suspension(api_client, db, world, tom):
    david = world["david"]
    _grant(api_client, "test-tom", TALENT, david.id, "TA_MEMBER", [ABC])
    preview = api_client.get(f"/api/access/{TALENT}/users/{david.id}/revoke-preview", headers=_h(api_client, "test-tom")).json()
    assert preview["allowed"] and preview["removes_direct"]["role"] == "TA_MEMBER" and preview["suspends"] == []
    resp = _revoke(api_client, "test-tom", TALENT, david.id)
    assert resp.status_code == 200 and resp.json()["has_access"] is False
    assert db.execute(select(ApplicationAccessSuspension)).first() is None
    assert _perms(db, david, TALENT) == frozenset()


def test_revoking_with_a_group_grant_suspends_only_this_app(api_client, db, world, tom):
    david = world["david"]
    group = _group(db, "ta-team", david, TALENT, "TA_MEMBER", clients=[(ABC, "cli-abc-company")])
    db.add(GroupModuleRole(access_group_id=group.id, module_key=BIRTHDAY, role="BIRTHDAY_USER"))
    db.commit()
    preview = api_client.get(f"/api/access/{TALENT}/users/{david.id}/revoke-preview", headers=_h(api_client, "test-tom")).json()
    assert preview["allowed"] and [s["group_name"] for s in preview["suspends"]] == ["ta-team"]
    before = _av(db, david)
    assert _revoke(api_client, "test-tom", TALENT, david.id).status_code == 200
    assert _perms(db, david, TALENT) == frozenset()  # suspended in DijiTalentFlow
    assert "birthday.dashboard.read" in _perms(db, david, BIRTHDAY)  # the same group still applies elsewhere
    assert db.execute(select(UserGroupMembership).where(UserGroupMembership.user_id == david.id)).first() is not None
    assert _av(db, david) > before
    listed = api_client.get(f"/api/access/{TALENT}/users/{david.id}", headers=_h(api_client, "test-tom")).json()
    assert listed["suspension"]["reason"] == "Left the team" and listed["sources"][0]["applies"] is False
    # Granting again lifts the suspension (audited), and the group applies again too.
    assert _grant(api_client, "test-tom", TALENT, david.id, "TA_MEMBER", [ABC]).status_code == 200
    assert db.execute(select(ApplicationAccessSuspension)).first() is None
    actions = set(db.execute(select(AuditLog.action)).scalars())
    assert {"module_access.suspended", "module_access.suspension_lifted"} <= actions


# Mandatory access, shown with a module-neutral default role: here BIRTHDAY_USER is made the default
# role for every eligible employee (the same shape as the real always-on default access).
USER_PERMS = frozenset({"birthday.dashboard.read", "birthday.orders.read", "birthday.suppliers.read"})


@pytest.fixture()
def default_access(db, world):
    db.add(ModuleBaselineRole(module_key=BIRTHDAY, role="BIRTHDAY_USER", enabled=True))
    db.commit()
    return world


def test_mandated_access_survives_revocation(api_client, db, default_access):
    world = default_access
    hal = world["hal"]
    assert _appoint(api_client, BIRTHDAY, world["tom"].id, ["BIRTHDAY_ADMIN"]).status_code == 200
    _group(db, "all-staff", hal, BIRTHDAY, "BIRTHDAY_ADMIN", system=True)
    # Only mandatory access: nothing to remove.
    resp = _revoke(api_client, "test-tom", BIRTHDAY, hal.id)
    assert resp.status_code == 409  # only default access and a SYSTEM group: nothing removable
    assert "birthday.orders.create" in _perms(db, hal, BIRTHDAY)
    # A direct grant on top is removable; the default access stays.
    assert _grant(api_client, "test-tom", BIRTHDAY, world["erin"].id, "BIRTHDAY_ADMIN").status_code == 200
    assert _revoke(api_client, "test-tom", BIRTHDAY, world["erin"].id).status_code == 200
    assert _perms(db, world["erin"], BIRTHDAY) == USER_PERMS


def test_suspension_never_removes_default_access(db, default_access):
    hal = db.get(User, default_access["hal"].id)
    db.add(ApplicationAccessSuspension(user_id=hal.id, module_key=BIRTHDAY, reason="x"))
    db.commit()
    assert _perms(db, hal, BIRTHDAY) == USER_PERMS


def test_suspended_group_scope_outside_authority_cannot_be_removed(api_client, db, world, tom):
    david = world["david"]
    _group(db, "xyz-team", david, TALENT, "TA_MEMBER", clients=[(XYZ, "cli-xyz-company")])
    preview = api_client.get(f"/api/access/{TALENT}/users/{david.id}/revoke-preview", headers=_h(api_client, "test-tom")).json()
    assert not preview["allowed"] and "outside your authority" in preview["reason"]
    assert _revoke(api_client, "test-tom", TALENT, david.id).status_code == 403


def test_central_admin_lifts_a_suspension_and_sees_it(api_client, db, world, tom):
    david = world["david"]
    _group(db, "ta-team", david, TALENT, "TA_MEMBER", clients=[(ABC, "cli-abc-company")])
    _revoke(api_client, "test-tom", TALENT, david.id)
    headers = _h(api_client, "test-platform-admin")
    listed = api_client.get(f"{ADMIN}/applications/{TALENT}/suspensions", headers=headers).json()
    assert [s["user_id"] for s in listed] == [david.id]
    eff = api_client.get(f"{ADMIN}/users/{david.id}/effective-access", headers=headers).json()
    assert eff["suspended_modules"] == [TALENT]
    assert api_client.delete(f"{ADMIN}/applications/{TALENT}/suspensions/{david.id}", headers=headers).status_code == 200
    assert "talent.requests.read" in _perms(db, david, TALENT)
    lifted = db.execute(select(AuditLog).where(AuditLog.action == "module_access.suspension_lifted")).scalars().one()
    assert '"channel": "CENTRAL"' in lifted.event_metadata


# --- onboarding ------------------------------------------------------------------------------------


@pytest.fixture()
def directory():
    provider = MockDirectoryProvider(users=[
        _person(OID_NEW, "Nina New", "nina@example.com"),
        _person(OID_NOHR, "Sam Service", "svc@example.com"),
    ])
    set_directory_provider(provider)
    set_employee_record_checker(_Records({"svc@example.com": "NOT_FOUND"}))
    return provider


def test_search_finds_eligible_people_and_matched_directory_employees(api_client, world, tom, directory):
    headers = _h(api_client, "test-tom")
    assert api_client.get(f"/api/access/{TALENT}/people?q=a", headers=headers).status_code == 400
    found = api_client.get(f"/api/access/{TALENT}/people?q=nin", headers=headers).json()
    assert [(p["source"], p["entra_object_id"]) for p in found["people"]] == [("DIRECTORY", OID_NEW)]
    # Not in HR: shown with the reason, never grantable (a directory entry alone is not eligibility).
    sam = api_client.get(f"/api/access/{TALENT}/people?q=sam", headers=headers).json()["people"]
    assert [(p["entra_object_id"], p["can_grant"]) for p in sam] == [(OID_NOHR, False)]
    assert "BambooHR" in sam[0]["reason"]
    people = api_client.get(f"/api/access/{TALENT}/people?q=david", headers=headers).json()["people"]
    assert people[0]["user_id"] == world["david"].id and people[0]["can_grant"]
    outsider = api_client.get(f"/api/access/{TALENT}/people?q=outsider", headers=headers).json()["people"]
    assert outsider == []  # not an eligible employee and no access here: not listed


def test_onboarding_creates_and_grants_in_one_transaction(api_client, db, world, tom, directory):
    resp = api_client.post(f"/api/access/{TALENT}/users/from-directory", headers=_h(api_client, "test-tom"), json={
        "entra_object_id": OID_NEW, "role": "TA_MEMBER", "client_scope": {"all_clients": False, "client_ids": [ABC]},
    })
    assert resp.status_code == 201, resp.text
    nina = db.execute(select(User).where(User.email == "nina@example.com")).scalars().one()
    assert nina.platform_role == "PLATFORM_USER" and AuthorizationService.is_eligible_employee(nina)
    assert "talent.requests.read" in _perms(db, nina, TALENT)
    created = db.execute(select(AuditLog).where(AuditLog.action == "user.created")).scalars().one()
    assert "APPLICATION_ONBOARDING" in created.new_state


@pytest.mark.parametrize(("oid", "status"), [(OID_NOHR, "NOT_FOUND"), (OID_NEW, "UNKNOWN")])
def test_onboarding_without_a_matched_hr_record_creates_nothing(api_client, db, world, tom, directory, oid, status):
    if status == "UNKNOWN":
        set_employee_record_checker(_Records({"nina@example.com": "UNKNOWN"}))
    count = len(db.execute(select(User)).all())
    resp = api_client.post(f"/api/access/{TALENT}/users/from-directory", headers=_h(api_client, "test-tom"), json={
        "entra_object_id": oid, "role": "TA_MEMBER", "client_scope": {"all_clients": False, "client_ids": [ABC]},
    })
    assert resp.status_code == 400
    db.expire_all()
    assert len(db.execute(select(User)).all()) == count


def test_onboarding_outside_authority_creates_nothing(api_client, db, world, tom, directory):
    resp = api_client.post(f"/api/access/{TALENT}/users/from-directory", headers=_h(api_client, "test-tom"), json={
        "entra_object_id": OID_NEW, "role": "TA_MANAGER", "client_scope": {"all_clients": False, "client_ids": [ABC]},
    })
    assert resp.status_code == 403
    assert db.execute(select(User).where(User.email == "nina@example.com")).first() is None


# --- administrators ---------------------------------------------------------------------------------


def test_secondary_appointments_are_off_by_default_and_never_exceed_authority(api_client, db, world, tom):
    headers = _h(api_client, "test-tom")
    body = {"grantable_roles": ["TA_MEMBER"], "client_authority": {"client_ids": [ABC]}}
    assert api_client.put(f"/api/access/{TALENT}/admins/{world['erin'].id}", json=body, headers=headers).status_code == 403
    assert _appoint(api_client, TALENT, tom.id, ["TA_MEMBER"], [ABC], can_appoint=True).status_code == 200
    wider = {"grantable_roles": ["TA_MEMBER", "TA_MANAGER"], "client_authority": {"client_ids": [ABC]}}
    assert api_client.put(f"/api/access/{TALENT}/admins/{world['erin'].id}", json=wider, headers=headers).status_code == 403
    xyz = {"grantable_roles": ["TA_MEMBER"], "client_authority": {"client_ids": [XYZ]}}
    assert api_client.put(f"/api/access/{TALENT}/admins/{world['erin'].id}", json=xyz, headers=headers).status_code == 403
    owner = {**body, "can_appoint_admins": True}
    assert api_client.put(f"/api/access/{TALENT}/admins/{world['erin'].id}", json=owner, headers=headers).status_code == 403
    assert api_client.put(f"/api/access/{TALENT}/admins/{world['erin'].id}", json=body, headers=headers).status_code == 200
    assert api_client.delete(f"/api/access/{TALENT}/admins/{tom.id}", headers=headers).status_code == 403  # self
    assert api_client.delete(f"/api/access/{TALENT}/admins/{world['erin'].id}", headers=headers).status_code == 200


def test_super_admin_may_remove_the_last_administrator_and_it_is_flagged(api_client, db, world, tom):
    resp = api_client.delete(f"{ADMIN}/applications/{TALENT}/administrators/{tom.id}", headers=_h(api_client, "test-super-admin"))
    assert resp.status_code == 200
    removed = db.execute(select(AuditLog).where(AuditLog.action == "application_admin.removed")).scalars().one()
    assert '"last_administrator": true' in removed.event_metadata
    assert TALENT not in build_claims(db.get(User, tom.id), db)["module_roles"]


def test_super_admin_self_appointment_needs_break_glass(api_client, db, world):
    super_admin = world["super_admin"]
    assert _appoint(api_client, TALENT, super_admin.id, ["TA_MEMBER"], [ABC]).status_code == 403
    resp = _appoint(api_client, TALENT, super_admin.id, ["TA_MEMBER"], [ABC], break_glass_reason="Covering for Tom today")
    assert resp.status_code == 200
    entry = db.execute(select(AuditLog).where(AuditLog.action == "application_admin.appointed")).scalars().one()
    assert '"break_glass": true' in entry.event_metadata


# --- precedence, disablement, consistency -----------------------------------------------------------


def test_disabling_an_application_removes_it_and_revokes_sessions(api_client, db, world, tom):
    david = world["david"]
    _grant(api_client, "test-tom", TALENT, david.id, "TA_MEMBER", [ABC])
    before = _av(db, david)
    resp = api_client.patch(f"{ADMIN}/modules/{TALENT}", json={"enabled": False}, headers=_h(api_client, "test-platform-admin"))
    assert resp.status_code == 200 and resp.json()["enabled"] is False
    assert _av(db, david) > before  # every existing session is revoked and refreshes without the app
    assert TALENT not in build_claims(db.get(User, david.id), db)["module_roles"]
    assert TALENT not in build_claims(db.get(User, world["gina"].id), db)["module_roles"]  # direct grants too
    assert api_client.get(f"/api/access/{TALENT}/users", headers=_h(api_client, "test-tom")).status_code == 403
    assert api_client.patch(f"{ADMIN}/modules/{TALENT}", json={"enabled": True},
                            headers=_h(api_client, "test-ta")).status_code == 403  # registry is admin-only


def test_central_and_delegated_grants_produce_identical_access(api_client, db, world, tom):
    david, erin = world["david"], world["erin"]
    assert _grant(api_client, "test-tom", TALENT, david.id, "TA_MEMBER", [ABC]).status_code == 200
    central = api_client.put(f"{ADMIN}/users/{erin.id}/modules/{TALENT}", headers=_h(api_client, "test-super-admin"),
                             json={"role": "TA_MEMBER", "client_scope": {"all_clients": False, "client_ids": [ABC]}})
    assert central.status_code == 200
    db.expire_all()
    a = build_claims(db.get(User, david.id), db)["module_roles"][TALENT]
    b = build_claims(db.get(User, erin.id), db)["module_roles"][TALENT]
    assert a == b
    channels = [e for e in db.execute(select(AuditLog.event_metadata).where(
        AuditLog.action == "module_assignment.created")).scalars()]
    assert any('"APPLICATION"' in c for c in channels) and any('"CENTRAL"' in c for c in channels)


def test_role_holders_follow_effective_access(api_client, db, world, tom):
    david, erin = world["david"], world["erin"]
    _group(db, "cs", erin, TALENT, "CUSTOMER_SUCCESS", clients=[(ABC, "cli-abc-company")])
    _grant(api_client, "test-tom", TALENT, david.id, "CUSTOMER_SUCCESS", [ABC])

    def holders(role):
        url = f"/api/platform/internal/module-roles/{TALENT}/{role}/user-ids"
        return api_client.get(url, headers=internal_headers()).json()["user_ids"]

    assert set(holders("CUSTOMER_SUCCESS")) >= {david.id, erin.id}  # direct and group
    assert tom.id in holders("TALENT_ACCESS_ADMIN")
    _revoke(api_client, "test-tom", TALENT, erin.id)  # suspends the group grant in this app
    assert erin.id not in holders("CUSTOMER_SUCCESS")


def test_rollback_check_reports_appointments_and_suspensions(api_client, db, world, tom):
    result = rollback_check(db)
    assert not result.safe and result.appointments == [(TALENT, "tom@example.com")]
    db.query(ApplicationAdministrator).delete()
    db.commit()
    assert rollback_check(db).safe
