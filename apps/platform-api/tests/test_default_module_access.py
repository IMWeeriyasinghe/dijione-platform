"""Default DijiAtWork access: derived for every active DijiOne user, never stored.

Everyone active holds ATWORK_USER and can open DijiAtWork. Only an eligible employee (verified
internal identity + employee record) also gets the attendance permissions; for anyone else the
default grant carries ``atwork.access`` alone, so attendance actions stay closed."""

import threading
import time

import pytest

from app.api.deps import Viewer, get_current_user, get_viewer
from app.api.routes.auth import issue_user_session
from app.core.config import get_settings
from app.integrations.people import EmployeeRecord, EmployeeRecordChecker, set_employee_record_checker
from app.main import app
from app.models.access_group import AccessGroup, GroupModuleRole, UserGroupMembership
from app.models.module import ApplicationModule
from app.models.module_baseline import ModuleBaselineRole
from app.models.user import User, UserModuleRole
from app.services import entra_service
from app.services.authorization_service import AuthorizationService
from app.services.claims_service import build_claims
from app.services.directory_service import DirectoryService
from app.services.entra_service import resolve_entra_user
from tests.conftest import auth_headers, internal_headers
from tests.test_atwork_registration import MANAGER_PERMS, USER_PERMS, _register_module

TENANT = "tenant-1"
ISS = f"https://login.microsoftonline.com/{TENANT}/v2.0"
USERS_URL = "/api/platform/admin/users"
ACCESS_ONLY = frozenset({"atwork.access"})
ATTENDANCE = USER_PERMS - ACCESS_ONLY


@pytest.fixture(autouse=True)
def _entra_settings(monkeypatch):
    monkeypatch.setenv("ENTRA_TENANT_ID", TENANT)
    monkeypatch.setenv("ENTRA_INTERNAL_EMAIL_DOMAINS", "dijital.example")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_viewer, None)


@pytest.fixture()
def baseline(db):
    _register_module(db)
    db.add(ModuleBaselineRole(module_key="atwork", role="ATWORK_USER", enabled=True))
    db.commit()


def tok(name="emp", **over):
    return {"oid": f"oid-{name}", "email": f"{name}@dijital.example", "name": name, "tid": TENANT, "iss": ISS, "acct": 0, **over}


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
    assert atwork(db, user) == ACCESS_ONLY  # active platform user: the app, before any match
    assert atwork(db, sign_in(db)) == USER_PERMS


def test_new_employee_gets_default_access_at_first_sign_in(db, baseline):
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
        {"acct": None},
        {"preferred_username": "x_y.com#EXT#@tenant.example", "email": None},
        {"upn": "ext#EXT#@dijital.example"},
        {"email": "person@gmail.example"},
    ],
)
def test_guest_and_foreign_identities_get_no_attendance_actions(db, baseline, over):
    claims = {**tok(), **over}
    email = (claims.get("email") or claims.get("preferred_username")).lower()
    user = User(email=email, full_name="x", is_active=True, entra_object_id="oid-emp", identity_provider="ENTRA")
    db.add(user)
    db.commit()
    assert atwork(db, resolve_entra_user(db, claims)) & ATTENDANCE == frozenset()


def test_empty_domain_list_fails_closed_for_attendance(db, baseline, monkeypatch):
    monkeypatch.setenv("ENTRA_INTERNAL_EMAIL_DOMAINS", "")
    get_settings.cache_clear()
    user = existing(db)
    user.entra_object_id = "oid-emp"
    db.commit()
    assert atwork(db, sign_in(db)) == ACCESS_ONLY


def test_losing_eligibility_at_next_sign_in_removes_attendance_actions(db, baseline):
    existing(db)
    sign_in(db)
    assert atwork(db, sign_in(db, idp="live.com")) == ACCESS_ONLY


def test_inactive_user_has_no_default_access(db, baseline):
    existing(db)
    user = sign_in(db)
    user.is_active = False
    db.commit()
    assert atwork(db, user) == frozenset()


def test_dev_persona_is_not_an_attendance_identity(db, baseline):
    user = User(email="p@dijital.example", full_name="p", persona_key="p1", internal_employee=True)
    db.add(user)
    db.commit()
    assert atwork(db, user) == ACCESS_ONLY


def test_existing_administrator_gets_default_access_and_no_admin_permissions(db, baseline):
    admin = User(email="adm@dijital.example", full_name="adm", is_active=True, platform_role="SUPER_ADMIN")
    db.add(admin)
    db.commit()
    roles = AuthorizationService(db).effective_module_roles(admin)
    assert [(g.role, g.source_type) for g in roles["atwork"]] == [("ATWORK_USER", "BASELINE")]
    assert atwork(db, admin) == ACCESS_ONLY
    assert not any(p.startswith("atwork.management") for p in atwork(db, admin))


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


def test_default_access_is_always_on_a_disabled_row_does_not_remove_it(db, baseline):
    existing(db)
    user = sign_in(db)
    db.add(UserModuleRole(user_id=user.id, module_key="atwork", role="ATWORK_USER", enabled=False))
    db.commit()
    assert atwork(db, user) == USER_PERMS


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
    outsider_access = api_client.get(f"{USERS_URL}/{outsider.id}/effective-access", headers=admin).json()
    module = next(m for m in outsider_access["modules"] if m["module_key"] == "atwork")
    assert set(module["permissions"]) == ACCESS_ONLY

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_viewer] = lambda: Viewer(user=user)
    assert "atwork" in {m["key"] for m in api_client.get("/api/modules").json()}
    assert {"module_key": "atwork", "role": "ATWORK_USER", "client_id": None, "enabled": True} in [
        {k: v for k, v in e.items() if k in ("module_key", "role", "client_id", "enabled")}
        for e in api_client.get("/api/auth/me").json()["module_roles"]
    ]
    # An active user with no employee match still sees and opens DijiAtWork (access only).
    app.dependency_overrides[get_current_user] = lambda: outsider
    app.dependency_overrides[get_viewer] = lambda: Viewer(user=outsider)
    assert "atwork" in {m["key"] for m in api_client.get("/api/modules").json()}


def test_missing_membership_claim_is_not_proof(db, baseline):
    user = existing(db)
    user.entra_object_id = "oid-emp"
    db.commit()
    claims = tok()
    del claims["acct"]
    assert atwork(db, resolve_entra_user(db, claims)) == ACCESS_ONLY


def test_a_higher_role_keeps_the_standard_role_alongside_it(api_client, db, baseline, two_tenant_world):
    existing(db)
    user = sign_in(db)
    _grant_group(db, user)
    assert USER_PERMS <= atwork(db, user) and MANAGER_PERMS <= atwork(db, user)
    admin = auth_headers(api_client, "test-super-admin")
    body = api_client.get(f"{USERS_URL}/{user.id}/effective-access", headers=admin).json()
    assert body["default_access_excluded"] == []
    assert [s["type"] for m in body["modules"] for s in m["sources"] if m["module_key"] == "atwork"] == ["GROUP", "BASELINE"]
    # The standard role cannot be removed while a higher one is held, nor after it goes.
    assert api_client.delete(f"{USERS_URL}/{user.id}/modules/atwork", headers=admin).status_code == 409
    assert atwork(db, user) >= MANAGER_PERMS


def test_live_permissions_follow_revocation_and_deactivation(api_client, db, baseline):
    url_for = lambda u: f"/api/platform/internal/users/{u.id}/modules/atwork/permissions"  # noqa: E731
    existing(db)
    user = sign_in(db)
    member = _grant_group(db, user)
    headers = internal_headers()
    assert set(api_client.get(url_for(user), headers=headers).json()["permissions"]) == MANAGER_PERMS
    db.delete(member)
    db.commit()
    assert set(api_client.get(url_for(user), headers=headers).json()["permissions"]) == USER_PERMS
    user.is_active = False
    db.commit()
    assert api_client.get(url_for(user), headers=headers).json() == {"active": False, "permissions": []}
    assert api_client.get(url_for(user)).status_code == 401


def first_signin(name="new", **over):
    return tok(name, **over)


class _Records(EmployeeRecordChecker):
    """Matches only the given addresses; everyone else is NOT_FOUND."""

    def __init__(self, matched=()):
        self.matched = set(matched)

    def check(self, *, email, employee_id=None, cached_only=False, wait_seconds=0.0):
        return EmployeeRecord("MATCHED" if email in self.matched else "NOT_FOUND", employee_number="0042")


# --- First-time sign-in: the baseline is separate from automatic DijiOne onboarding ------------------------------------

def test_matched_new_employee_gets_atwork_and_nothing_else(db, baseline, api_client):
    set_employee_record_checker(_Records({"new@dijital.example"}))
    user = resolve_entra_user(db, first_signin())
    assert user.employee_record_status == "MATCHED"
    roles = AuthorizationService(db).effective_module_roles(user)
    assert set(roles) == {"atwork"} and [g.role for g in roles["atwork"]] == ["ATWORK_USER"]
    assert AuthorizationService(db).effective_permissions(user, "atwork") == USER_PERMS
    headers = {"Authorization": f"Bearer {issue_user_session(user, db)}"}
    assert "atwork" in {m["key"] for m in api_client.get("/api/modules", headers=headers).json()}  # DijiOne Home
    live = api_client.get(f"/api/platform/internal/users/{user.id}/modules/atwork/permissions",
                          headers=internal_headers())  # what atwork-api checks on every request
    assert live.status_code == 200 and set(live.json()["permissions"]) == USER_PERMS


def test_internal_service_account_opens_atwork_without_attendance_access(db, baseline, api_client):
    set_employee_record_checker(_Records())
    svc = resolve_entra_user(db, first_signin("svc"))
    assert svc.is_active and svc.employee_record_status == "NOT_FOUND"  # also: not in BambooHR
    assert AuthorizationService(db).effective_permissions(svc, "atwork") == ACCESS_ONLY
    headers = {"Authorization": f"Bearer {issue_user_session(svc, db)}"}
    assert "atwork" in {m["key"] for m in api_client.get("/api/modules", headers=headers).json()}
    live = api_client.get(f"/api/platform/internal/users/{svc.id}/modules/atwork/permissions",
                          headers=internal_headers())
    assert set(live.json()["permissions"]) == ACCESS_ONLY  # atwork-api refuses check-in without record_own


class _SlowSnapshot(EmployeeRecordChecker):
    """A real checker whose people-api source answers after ``delay`` seconds, counting calls."""

    def __init__(self, delay, emails):
        class _Source:
            calls = 0

            def active_employees(src):
                src.calls += 1
                time.sleep(delay)
                return [{"work_email": e, "employee_number": "7", "employment_status": "Active"} for e in emails]

            def active_workforce(src):
                return []
        self.source = _Source()
        super().__init__(source=self.source)


def test_first_sign_in_waits_for_a_loading_hr_snapshot(db, baseline):
    checker = _SlowSnapshot(0.3, ["new@dijital.example"])
    set_employee_record_checker(checker)
    user = resolve_entra_user(db, first_signin())
    assert user.employee_record_status == "MATCHED"
    assert AuthorizationService(db).effective_permissions(user, "atwork") == USER_PERMS
    assert checker.source.calls == 1


def test_slow_hr_source_never_blocks_sign_in_and_reconciliation_completes_entitlement(db, baseline, monkeypatch):
    monkeypatch.setattr(entra_service, "FIRST_SIGNIN_HR_WAIT_SECONDS", 0.2)
    checker = _SlowSnapshot(1.0, ["new@dijital.example"])
    set_employee_record_checker(checker)
    started = time.monotonic()
    user = resolve_entra_user(db, first_signin())
    assert time.monotonic() - started < 0.9  # bounded wait, the load continues in the background
    assert user.is_active and user.employee_record_status == "UNKNOWN"
    assert AuthorizationService(db).effective_permissions(user, "atwork") == ACCESS_ONLY  # not yet eligible
    for t in threading.enumerate():
        if t.name == "employee-records-warm":
            t.join(3)
    assert checker.source.calls == 1  # the sign-in started one background load, never more
    DirectoryService(db).reconcile_employee_records(actor=None)  # no manual assignment
    db.refresh(user)
    assert user.employee_record_status == "MATCHED"
    assert AuthorizationService(db).effective_permissions(user, "atwork") == USER_PERMS
