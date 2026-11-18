"""/api/auth/me carries a read-only access summary for the header: per application the primary role's
name, every contributing grant (source, group, mandatory, administrative) and the client scope; plus
the platform role's name. It is computed by the same resolution as the session token."""

import pytest

from app.core.config import get_settings
from app.models.access_group import AccessGroup, GroupModuleRole, UserGroupMembership
from app.models.application_access import ApplicationAdministrator
from app.models.module import ApplicationModule
from app.models.module_baseline import ModuleBaselineRole
from app.models.user import User, UserModuleRole
from tests.conftest import assign_client_scope, auth_headers, make_eligible

TALENT, BIRTHDAY = "talent-flow", "birthday"


@pytest.fixture()
def person(db, two_tenant_world):
    db.add_all([
        ApplicationModule(key=TALENT, name="DijiTalentFlow", description="", route="/talent-flow"),
        ApplicationModule(key=BIRTHDAY, name="DIJI Birthday", description="", route="/birthday",
                          supports_client_scope=False),
        ModuleBaselineRole(module_key=BIRTHDAY, role="BIRTHDAY_USER", enabled=True),
    ])
    user = make_eligible(User(email="pat@example.com", full_name="Pat", persona_key="test-pat"))
    db.add(user)
    db.flush()
    direct = UserModuleRole(user_id=user.id, module_key=TALENT, role="TA_MEMBER")
    db.add(direct)
    db.flush()
    assign_client_scope(db, direct, client_id=1)
    group = AccessGroup(key="cs", display_name="CS Team")
    db.add(group)
    db.flush()
    db.add_all([
        UserGroupMembership(user_id=user.id, access_group_id=group.id),
        GroupModuleRole(access_group_id=group.id, module_key=TALENT, role="CUSTOMER_SUCCESS"),
        ApplicationAdministrator(user_id=user.id, module_key=TALENT, grantable_roles=["TA_MEMBER"]),
    ])
    db.commit()
    return user


def _me(api_client):
    return api_client.get("/api/auth/me", headers=auth_headers(api_client, "test-pat")).json()


def test_application_entry_lists_every_grant_with_its_source(api_client, person):
    me = _me(api_client)
    assert me["platform_role"] == "PLATFORM_USER" and me["platform_role_name"] == "Platform User"
    talent = next(e for e in me["module_roles"] if e["module_key"] == TALENT)
    assert talent["role"] == "TA_MEMBER" and talent["role_name"] == "Talent Acquisition Member"  # direct is primary
    sources = [(g["source"], g["role"], g["group_name"], g["administrative"]) for g in talent["grants"]]
    assert sources == [
        ("DIRECT", "TA_MEMBER", None, False),
        ("GROUP", "CUSTOMER_SUCCESS", "CS Team", False),
        ("APPOINTMENT", "TALENT_ACCESS_ADMIN", None, True),
    ]
    # The group grant has no client rows (unrestricted), so the union is all clients.
    assert talent["client_scope"] == {"all_clients": True, "clients": []}


def test_mandatory_default_access_and_unscoped_apps(api_client, person):
    birthday = next(e for e in _me(api_client)["module_roles"] if e["module_key"] == BIRTHDAY)
    assert birthday["grants"] == [{"role": "BIRTHDAY_USER", "role_name": "HR/Birthday User", "source": "BASELINE",
                                   "group_name": None, "mandatory": True, "administrative": False}]
    assert birthday["client_scope"] is None  # the application does not read client scope


def test_scoped_role_lists_client_names(api_client, db, person):
    db.query(UserGroupMembership).delete()
    db.commit()
    talent = next(e for e in _me(api_client)["module_roles"] if e["module_key"] == TALENT)
    assert talent["client_scope"] == {"all_clients": False, "clients": ["ABC Company"]}


def test_view_as_shows_the_viewed_employee(api_client, db, person, two_tenant_world, monkeypatch):
    monkeypatch.setenv("VIEW_AS_ENABLED", "true")
    get_settings.cache_clear()
    make_eligible(db.get(User, two_tenant_world["super_admin"].id))
    db.commit()
    started = api_client.post("/api/platform/admin/view-as", json={"target_user_id": person.id},
                              headers=auth_headers(api_client, "test-super-admin"))
    assert started.status_code == 201, started.text
    me = api_client.get("/api/auth/me", headers={"Authorization": f"Bearer {started.json()['access_token']}"}).json()
    assert me["id"] == person.id and {e["module_key"] for e in me["module_roles"]} >= {TALENT, BIRTHDAY}
    get_settings.cache_clear()
