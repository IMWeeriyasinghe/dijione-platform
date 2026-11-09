"""Default employee access: derived for eligible internal employees, never stored."""

import pytest

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.main import app
from app.models.access_group import AccessGroup, GroupModuleRole, UserGroupMembership
from app.models.module import ApplicationModule
from app.models.module_baseline import ModuleBaselineRole
from app.models.user import User, UserModuleRole
from app.services.authorization_service import AuthorizationService
from app.services.claims_service import build_claims
from app.services.entra_service import EntraLoginRefusedError, resolve_entra_user
from tests.conftest import auth_headers
from tests.test_atwork_registration import MANAGER_PERMS, USER_PERMS, _register_module

TENANT = "tenant-1"
USERS_URL = "/api/platform/admin/users"


@pytest.fixture(autouse=True)
def _entra_settings(monkeypatch):
    monkeypatch.setenv("ENTRA_TENANT_ID", TENANT)
    monkeypatch.setenv("ENTRA_INTERNAL_EMAIL_DOMAINS", "dijital.example")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture()
def baseline(db):
    _register_module(db)
    db.add(ModuleBaselineRole(module_key="atwork", role="ATWORK_USER", enabled=True))
    db.commit()


def tok(name="emp", **over):
    return {"oid": f"oid-{name}", "email": f"{name}@dijital.example", "name": name, "tid": TENANT, **over}


def existing(db, name="emp", active=True):
    user = User(email=f"{name}@dijital.example", full_name=name, is_active=active)
    db.add(user)
    db.commit()
    return user


def sign_in(db, name="emp", **over):
    return resolve_entra_user(db, tok(name, **over))


def atwork(db, user):
    return AuthorizationService(db).effective_permissions(user, "atwork")


def test_existing_employee_gets_default_access_at_sign_in(db, baseline):
    user = existing(db)
    assert atwork(db, user) == frozenset()
    assert atwork(db, sign_in(db)) == USER_PERMS


def test_activated_new_employee_gets_default_access(db, baseline):
    with pytest.raises(EntraLoginRefusedError):
        sign_in(db, "new")
    user = db.query(User).filter_by(email="new@dijital.example").one()
    assert atwork(db, user) == frozenset()
    user.is_active = True
    db.commit()
    assert atwork(db, sign_in(db, "new")) == USER_PERMS


def test_no_role_rows_are_written(db, baseline):
    existing(db)
    sign_in(db)
    user = sign_in(db)
    assert db.query(UserModuleRole).filter_by(user_id=user.id).count() == 0


@pytest.mark.parametrize(
    "over",
    [
        {"tid": "other-tenant"},
        {"idp": "https://sts.windows.net/other/"},
        {"idp": "live.com"},
        {"acct": 1},
        {"preferred_username": "x_y.com#EXT#@tenant.example", "email": None},
        {"upn": "ext#EXT#@dijital.example"},
        {"email": "person@gmail.example"},
    ],
)
def test_guest_and_foreign_identities_are_denied(db, baseline, over):
    claims = {**tok(), **over}
    email = (claims.get("email") or claims.get("preferred_username")).lower()
    db.add(User(email=email, full_name="x", is_active=True))
    db.commit()
    assert atwork(db, resolve_entra_user(db, claims)) == frozenset()


def test_empty_domain_list_fails_closed(db, baseline, monkeypatch):
    monkeypatch.setenv("ENTRA_INTERNAL_EMAIL_DOMAINS", "")
    get_settings.cache_clear()
    existing(db)
    assert atwork(db, sign_in(db)) == frozenset()


def test_losing_eligibility_at_next_sign_in_removes_access(db, baseline):
    existing(db)
    sign_in(db)
    assert atwork(db, sign_in(db, idp="live.com")) == frozenset()


def test_inactive_user_has_no_default_access(db, baseline):
    existing(db)
    user = sign_in(db)
    user.is_active = False
    db.commit()
    assert atwork(db, user) == frozenset()


def test_dev_persona_is_not_eligible(db, baseline):
    user = User(email="p@dijital.example", full_name="p", persona_key="p1", internal_employee=True)
    db.add(user)
    db.commit()
    assert atwork(db, user) == frozenset()


def test_disabled_policy_and_disabled_module_grant_nothing(db, baseline):
    existing(db)
    user = sign_in(db)
    row = db.get(ModuleBaselineRole, "atwork")
    row.enabled = False
    db.commit()
    assert atwork(db, user) == frozenset()
    row.enabled = True
    db.query(ApplicationModule).filter_by(key="atwork").one().enabled = False
    db.commit()
    assert atwork(db, user) == frozenset()


def test_explicit_revocation_overrides_default(db, baseline):
    existing(db)
    user = sign_in(db)
    db.add(UserModuleRole(user_id=user.id, module_key="atwork", role="ATWORK_USER", enabled=False))
    db.commit()
    assert atwork(db, user) == frozenset()


def test_default_grants_no_management_and_touches_no_other_module(db, baseline):
    existing(db)
    user = sign_in(db)
    claims = build_claims(user, db)
    assert list(claims["module_roles"]) == ["atwork"]
    assert "atwork.management.access" not in claims["module_roles"]["atwork"]["permissions"]


def _grant_group(db, user):
    group = AccessGroup(key="supervisors", display_name="Supervisors")
    db.add(group)
    db.flush()
    member = UserGroupMembership(user_id=user.id, access_group_id=group.id)
    db.add_all([member, GroupModuleRole(access_group_id=group.id, module_key="atwork", role="ATWORK_MANAGER", enabled=True)])
    db.commit()
    return member


def test_group_manager_keeps_employee_access_and_removal_takes_it_away(db, baseline):
    existing(db)
    user = sign_in(db)
    member = _grant_group(db, user)
    assert atwork(db, user) == MANAGER_PERMS
    assert build_claims(user, db)["module_roles"]["atwork"]["role"] == "ATWORK_MANAGER"
    db.delete(member)
    db.commit()
    assert atwork(db, user) == USER_PERMS


def test_admin_grants_and_revokes_manager_ordinary_user_cannot(api_client, db, baseline, two_tenant_world):
    existing(db)
    user = sign_in(db)
    url = f"{USERS_URL}/{user.id}/modules/atwork"
    body = {"role": "ATWORK_MANAGER"}
    assert api_client.put(url, json=body, headers=auth_headers(api_client, "test-ta")).status_code == 403
    assert atwork(db, user) == USER_PERMS
    admin = auth_headers(api_client, "test-super-admin")
    assert api_client.put(url, json=body, headers=admin).status_code == 200
    db.expire_all()
    assert atwork(db, user) == MANAGER_PERMS
    assert api_client.delete(url, headers=admin).status_code == 200
    db.expire_all()
    assert atwork(db, user) == USER_PERMS


def test_home_admin_and_me_agree_with_effective_access(api_client, db, baseline, two_tenant_world):
    existing(db)
    user = sign_in(db)
    outsider = existing(db, "out")
    admin = auth_headers(api_client, "test-super-admin")
    effective = api_client.get(f"{USERS_URL}/{user.id}/effective-access", headers=admin).json()
    module = next(m for m in effective["modules"] if m["module_key"] == "atwork")
    assert set(module["permissions"]) == USER_PERMS and [s["type"] for s in module["sources"]] == ["BASELINE"]

    app.dependency_overrides[get_current_user] = lambda: user
    assert "atwork" in {m["key"] for m in api_client.get("/api/modules").json()}
    assert {"module_key": "atwork", "role": "ATWORK_USER", "client_id": None, "enabled": True} in api_client.get(
        "/api/auth/me"
    ).json()["module_roles"]
    app.dependency_overrides[get_current_user] = lambda: outsider
    assert "atwork" not in {m["key"] for m in api_client.get("/api/modules").json()}
