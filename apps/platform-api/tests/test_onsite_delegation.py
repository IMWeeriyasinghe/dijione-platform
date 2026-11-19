"""Diji On-site v0.9 two-role model with delegation (owner decision 2026-11-19).

Every On-site Admin (direct or group grant) is an implied access administrator of
Diji On-site who may grant, change and revoke **On-site User** (ONSITE_VIEWER) only.
No privilege escalation: never On-site Admin, never another administrator, never a
platform administrator or themselves, never appointing administrators. The authority
is computed on every request (demotion / suspension / feature switch take effect at
once) and an explicit appointment row always takes precedence. Other applications
have no implied rule."""

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.permissions import DELEGATION
from app.models.access_group import AccessGroup, GroupModuleRole, UserGroupMembership
from app.models.application_access import ApplicationAccessSuspension, ApplicationAdministrator
from app.models.audit_log import AuditLog
from app.models.module import ApplicationModule
from app.models.module_baseline import ModuleBaselineRole
from app.models.user import User, UserModuleRole
from app.services.claims_service import build_claims
from tests.conftest import auth_headers, make_eligible

ONSITE, TALENT, BIRTHDAY = "onsite", "talent-flow", "birthday"
ACCESS = "/api/access/onsite"


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
        ApplicationModule(key=ONSITE, name="Diji On-site", description="", route="/onsite",
                          supports_client_scope=False),
        ApplicationModule(key=TALENT, name="DijiTalentFlow", description="", route="/talent-flow"),
        ApplicationModule(key=BIRTHDAY, name="DIJI Birthday", description="", route="/birthday",
                          supports_client_scope=False),
    ])
    people = {}
    for key in ("ann", "ben", "cara", "dev", "eve"):
        user = User(email=f"{key}@example.com", full_name=key.title(), persona_key=f"test-{key}")
        make_eligible(user)
        db.add(user)
        people[key] = user
    outsider = User(email="outsider@example.com", full_name="Outsider", persona_key="test-outsider")
    db.add(outsider)
    people["outsider"] = outsider
    db.flush()
    # Ann and Cara are On-site Admins (direct); Ben has no On-site access yet; Dev manages TalentFlow.
    db.add_all([UserModuleRole(user_id=people["ann"].id, module_key=ONSITE, role="ONSITE_ADMIN"),
                UserModuleRole(user_id=people["cara"].id, module_key=ONSITE, role="ONSITE_ADMIN"),
                UserModuleRole(user_id=people["dev"].id, module_key=TALENT, role="TA_MANAGER"),
                UserModuleRole(user_id=people["outsider"].id, module_key=ONSITE, role="ONSITE_ADMIN")])
    db.commit()
    for name in ("super_admin", "platform_admin"):
        make_eligible(db.get(User, two_tenant_world[name].id))
    db.commit()
    return {**two_tenant_world, **people}


def _h(api_client, persona):
    return auth_headers(api_client, persona)


def _grant(api_client, who, user_id, role):
    return api_client.put(f"{ACCESS}/users/{user_id}", json={"role": role}, headers=_h(api_client, who))


def _revoke(api_client, who, user_id):
    return api_client.post(f"{ACCESS}/users/{user_id}/revoke", json={"reason": "No longer needs access"},
                           headers=_h(api_client, who))


def _onsite_claim(db, user):
    db.expire_all()
    return build_claims(db.get(User, user.id), db)["module_roles"].get(ONSITE)


def test_catalog_declares_the_implied_rule_for_onsite_only():
    assert DELEGATION[ONSITE].implied_by == (("ONSITE_ADMIN", ("ONSITE_VIEWER",)),)
    assert all(not d.implied_by for k, d in DELEGATION.items() if k != ONSITE)


def test_onsite_admin_is_an_implied_access_admin_limited_to_on_site_user(api_client, db, world):
    me = api_client.get(f"{ACCESS}/me", headers=_h(api_client, "test-ann")).json()
    assert me["is_admin"] is True and me["can_appoint_admins"] is False
    assert [r["key"] for r in me["grantable_roles"]] == ["ONSITE_VIEWER"]
    assert [r["name"] for r in me["grantable_roles"]] == ["On-site User"]
    claim = _onsite_claim(db, world["ann"])
    assert claim["role"] == "ONSITE_ADMIN"  # the business role stays primary
    assert {"onsite.access.manage", "onsite.exceptions.manage", "onsite.identity.manage"} <= set(claim["permissions"])
    assert "onsite.access.manage_admins" not in claim["permissions"]
    assert db.execute(select(ApplicationAdministrator)).first() is None  # never persisted


def test_grant_change_and_revoke_on_site_user(api_client, db, world):
    ben = world["ben"]
    resp = _grant(api_client, "test-ann", ben.id, "ONSITE_VIEWER")
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "ONSITE_VIEWER" and resp.json()["role_name"] == "On-site User"
    claim = _onsite_claim(db, ben)
    assert claim["role"] == "ONSITE_VIEWER" and "onsite.exceptions.manage" not in claim["permissions"]
    entry = db.execute(select(AuditLog).where(AuditLog.action == "module_assignment.created")).scalars().one()
    assert '"channel": "APPLICATION"' in entry.event_metadata and entry.actor_id == world["ann"].id
    assert _grant(api_client, "test-ann", ben.id, "ONSITE_VIEWER").status_code == 200  # change/re-save
    resp = _revoke(api_client, "test-ann", ben.id)
    assert resp.status_code == 200, resp.text
    assert _onsite_claim(db, ben) is None
    assert db.execute(select(AuditLog).where(AuditLog.actor_id == world["ann"].id)).scalars().all()


def test_no_privilege_escalation(api_client, db, world):
    ben, cara = world["ben"], world["cara"]
    assert _grant(api_client, "test-ann", ben.id, "ONSITE_ADMIN").status_code == 403  # cannot appoint admins
    assert _grant(api_client, "test-ann", ben.id, "ONSITE_ACCESS_ADMIN").status_code == 403
    assert _grant(api_client, "test-ann", cara.id, "ONSITE_VIEWER").status_code == 403  # another On-site Admin
    assert _revoke(api_client, "test-ann", cara.id).status_code == 403
    assert db.execute(select(UserModuleRole).where(UserModuleRole.user_id == cara.id)).scalars().one().role \
        == "ONSITE_ADMIN"
    for target in ("ann", "super_admin", "platform_admin", "outsider"):
        assert _grant(api_client, "test-ann", world[target].id, "ONSITE_VIEWER").status_code == 403, target
    resp = api_client.put(f"/api/platform/admin/applications/{ONSITE}/administrators/{ben.id}",
                          json={"grantable_roles": ["ONSITE_VIEWER"], "can_appoint_admins": False},
                          headers=_h(api_client, "test-ann"))
    assert resp.status_code == 403  # appointing administrators stays with Super Admins
    users = api_client.get(f"{ACCESS}/users", headers=_h(api_client, "test-ann")).json()["users"]
    listed = {u["user_id"]: u for u in users}
    assert listed[cara.id]["manageable"] is False and "Platform or Super Admin" in listed[cara.id]["managed_reason"]


def test_demotion_removes_the_authority_immediately(api_client, db, world):
    ann = world["ann"]
    assert api_client.get(f"{ACCESS}/me", headers=_h(api_client, "test-ann")).json()["is_admin"]
    row = db.execute(select(UserModuleRole).where(UserModuleRole.user_id == ann.id)).scalars().one()
    row.role = "ONSITE_VIEWER"
    db.commit()
    assert api_client.get(f"{ACCESS}/me", headers=_h(api_client, "test-ann")).json()["is_admin"] is False
    assert api_client.get(f"{ACCESS}/users", headers=_h(api_client, "test-ann")).status_code == 403
    assert _grant(api_client, "test-ann", world["ben"].id, "ONSITE_VIEWER").status_code == 403
    assert "onsite.access.manage" not in _onsite_claim(db, ann)["permissions"]


def test_suspension_ineligibility_and_switch_remove_it(api_client, db, world, monkeypatch):
    db.add(ApplicationAccessSuspension(user_id=world["ann"].id, module_key=ONSITE, reason="synthetic",
                                       suspended_by_user_id=world["super_admin"].id))
    db.commit()
    assert api_client.get(f"{ACCESS}/me", headers=_h(api_client, "test-ann")).json()["is_admin"] is False
    assert _onsite_claim(db, world["ann"]) is None
    # Not an eligible employee: an On-site Admin grant implies nothing.
    assert api_client.get(f"{ACCESS}/me", headers=_h(api_client, "test-outsider")).json()["is_admin"] is False
    assert "onsite.access.manage" not in (_onsite_claim(db, world["outsider"]) or {}).get("permissions", [])
    monkeypatch.setenv("DELEGATED_ACCESS_ENABLED", "false")
    get_settings.cache_clear()
    assert api_client.get(f"{ACCESS}/users", headers=_h(api_client, "test-cara")).status_code == 404


def test_group_grant_implies_but_baseline_does_not(api_client, db, world):
    eve = world["eve"]
    group = AccessGroup(key="onsite-admins-synthetic", display_name="On-site admins (synthetic)")
    db.add(group)
    db.flush()
    db.add_all([GroupModuleRole(access_group_id=group.id, module_key=ONSITE, role="ONSITE_ADMIN"),
                UserGroupMembership(user_id=eve.id, access_group_id=group.id)])
    db.commit()
    me = api_client.get(f"{ACCESS}/me", headers=_h(api_client, "test-eve")).json()
    assert me["is_admin"] and [r["key"] for r in me["grantable_roles"]] == ["ONSITE_VIEWER"]
    # A baseline (default employee access) never implies administration.
    db.delete(db.execute(select(UserGroupMembership).where(UserGroupMembership.user_id == eve.id)).scalars().one())
    db.add(ModuleBaselineRole(module_key=ONSITE, role="ONSITE_ADMIN"))
    db.commit()
    assert api_client.get(f"{ACCESS}/me", headers=_h(api_client, "test-eve")).json()["is_admin"] is False


def test_explicit_appointment_takes_precedence(api_client, db, world):
    resp = api_client.put(f"/api/platform/admin/applications/{ONSITE}/administrators/{world['ann'].id}",
                          json={"grantable_roles": ["ONSITE_VIEWER", "ONSITE_ADMIN"], "can_appoint_admins": False},
                          headers=_h(api_client, "test-super-admin"))
    assert resp.status_code == 200, resp.text
    me = api_client.get(f"{ACCESS}/me", headers=_h(api_client, "test-ann")).json()
    assert [r["key"] for r in me["grantable_roles"]] == ["ONSITE_VIEWER", "ONSITE_ADMIN"]


def test_other_applications_unaffected(api_client, db, world):
    # A TalentFlow manager is not an access administrator of TalentFlow (no implied rule there).
    assert api_client.get(f"/api/access/{TALENT}/me", headers=_h(api_client, "test-dev")).json()["is_admin"] is False
    claims = build_claims(db.get(User, world["dev"].id), db)["module_roles"][TALENT]
    assert "talent.access.manage" not in claims["permissions"]
    # An On-site Admin gains nothing in other applications.
    assert api_client.get(f"/api/access/{BIRTHDAY}/me", headers=_h(api_client, "test-ann")).json()["is_admin"] is False
    assert api_client.get(f"/api/access/{TALENT}/users", headers=_h(api_client, "test-ann")).status_code == 403


# --- Add Person from Microsoft Entra (v0.9 closure) ----------------------------------------------
OID_NEW = "22222222-0000-4000-8000-000000000001"
OID_NOHR = "22222222-0000-4000-8000-000000000002"
OID_OTHER = "22222222-0000-4000-8000-000000000003"


@pytest.fixture()
def directory(world):
    from app.integrations.directory import DirectoryUser, MockDirectoryProvider, Photo, set_directory_provider
    from app.integrations.people import EmployeeRecord, EmployeeRecordChecker, set_employee_record_checker
    from app.services.directory_service import photo_cache

    def person(oid, name, email):
        return DirectoryUser(object_id=oid, display_name=name, email=email, user_principal_name=email,
                             job_title="Engineer", department="Ops", account_enabled=True, user_type="Member")

    class Records(EmployeeRecordChecker):
        def check(self, *, email, employee_id=None, cached_only=False):
            return EmployeeRecord("NOT_FOUND" if email == "nohr@example.com" else "MATCHED")

    # "dev@example.com" exists in DijiOne without this object id: a reused / unlinked address.
    provider = MockDirectoryProvider(
        users=[person(OID_NEW, "Nadia New", "nadia@example.com"), person(OID_NOHR, "Nolan NoHR", "nohr@example.com"),
               person(OID_OTHER, "Dev Twin", "dev@example.com")],
        photos={OID_NEW: Photo(content=b"\xff\xd8synthetic", content_type="image/jpeg")})
    set_directory_provider(provider)
    set_employee_record_checker(Records())
    photo_cache.clear() if hasattr(photo_cache, "clear") else None
    return provider


def test_add_person_searches_entra_and_onboards_a_new_eligible_user(api_client, db, world, directory):
    headers = _h(api_client, "test-ann")
    found = api_client.get(f"{ACCESS}/people?q=nad", headers=headers).json()
    assert [(p["entra_object_id"], p["can_grant"], p["user_principal_name"], p["has_photo"])
            for p in found["people"]] == [(OID_NEW, True, "nadia@example.com", True)]
    nohr = api_client.get(f"{ACCESS}/people?q=nolan", headers=headers).json()["people"]
    assert nohr[0]["can_grant"] is False and "BambooHR" in nohr[0]["reason"]
    assert api_client.post(f"{ACCESS}/users/from-directory", headers=headers,
                           json={"entra_object_id": OID_NEW, "role": "ONSITE_ADMIN"}).status_code == 403
    assert db.execute(select(User).where(User.email == "nadia@example.com")).first() is None  # nothing created
    resp = api_client.post(f"{ACCESS}/users/from-directory", headers=headers,
                           json={"entra_object_id": OID_NEW, "role": "ONSITE_VIEWER"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["role"] == "ONSITE_VIEWER" and body["role_name"] == "On-site User" and body["has_access"]
    assert body["recorded_change"]["action"] == "module_assignment.created"
    assert body["recorded_change"]["actor_name"] == "Ann"
    nadia = db.execute(select(User).where(User.email == "nadia@example.com")).scalars().one()
    assert nadia.entra_object_id == OID_NEW
    # Idempotent: adding the same directory person again links the same profile, never a duplicate.
    again = api_client.post(f"{ACCESS}/users/from-directory", headers=headers,
                            json={"entra_object_id": OID_NEW, "role": "ONSITE_VIEWER"})
    assert again.status_code == 201 and again.json()["user_id"] == nadia.id
    assert len(db.execute(select(User).where(User.email == "nadia@example.com")).all()) == 1
    assert _onsite_claim(db, nadia)["role"] == "ONSITE_VIEWER"


def test_object_id_is_authoritative_never_an_address_match(api_client, db, world, directory):
    headers = _h(api_client, "test-ann")
    twin = api_client.get(f"{ACCESS}/people?q=twin", headers=headers).json()["people"]
    assert [(p["entra_object_id"], p["can_grant"]) for p in twin] == [(OID_OTHER, False)]
    assert "not linked" in twin[0]["reason"]
    resp = api_client.post(f"{ACCESS}/users/from-directory", headers=headers,
                           json={"entra_object_id": OID_OTHER, "role": "ONSITE_VIEWER"})
    assert resp.status_code == 400 and "not linked" in resp.text
    dev = db.get(User, world["dev"].id)
    assert dev.entra_object_id != OID_OTHER and _onsite_claim(db, dev) is None  # the wrong person got nothing
    assert api_client.post(f"{ACCESS}/users/from-directory", headers=headers,
                           json={"entra_object_id": OID_NOHR, "role": "ONSITE_VIEWER"}).status_code == 400


def test_photos_only_through_the_access_routes_of_an_administrator(api_client, db, world, directory):
    ann, ben = _h(api_client, "test-ann"), _h(api_client, "test-ben")
    ok = api_client.get(f"{ACCESS}/people/{OID_NEW}/photo", headers=ann)
    assert ok.status_code == 200 and ok.headers["content-type"] == "image/jpeg"
    assert ok.headers["cache-control"].startswith("private")
    assert api_client.get(f"{ACCESS}/people/{OID_NOHR}/photo", headers=ann).status_code == 404  # no photo
    assert api_client.get(f"{ACCESS}/people/not-a-guid/photo", headers=ann).status_code == 404
    assert api_client.get(f"{ACCESS}/people/{OID_NEW}/photo", headers=ben).status_code == 403  # not an admin
    assert api_client.get(f"{ACCESS}/people/{OID_NEW}/photo").status_code == 401
    # Only enabled internal member accounts: never a guest (or an id the directory does not know).
    from app.integrations.directory import DirectoryUser, Photo
    guest = "22222222-0000-4000-8000-000000000004"
    directory.users.append(DirectoryUser(object_id=guest, display_name="Guest", email="guest@other.example",
                                         user_principal_name="guest_other#EXT#@example.com", job_title=None,
                                         department=None, account_enabled=True, user_type="Guest"))
    directory.photos[guest] = Photo(content=b"\xff\xd8guest", content_type="image/jpeg")
    assert api_client.get(f"{ACCESS}/people/{guest}/photo", headers=ann).status_code == 404
    assert api_client.get(f"{ACCESS}/people/22222222-0000-4000-8000-00000000000f/photo", headers=ann).status_code == 404
    directory.unavailable = True
    assert api_client.get("/api/access/onsite/people/22222222-0000-4000-8000-000000000009/photo",
                          headers=ann).status_code == 503
