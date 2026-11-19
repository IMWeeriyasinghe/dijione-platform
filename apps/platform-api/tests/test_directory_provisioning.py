"""Directory-backed provisioning, employee records (BambooHR), pre-login View-as, photos and Entra
groups. The directory and people-api are in-memory fakes; nothing here touches Microsoft Graph."""

import inspect
import re
import time

import httpx
import pytest

from app.api.deps import get_current_user, get_viewer
from app.core.config import get_settings
from app.integrations import directory as directory_module
from app.integrations.directory import (
    DirectoryGroup,
    DirectoryUser,
    GraphDirectoryProvider,
    MockDirectoryProvider,
    Photo,
    set_directory_provider,
)
from app.integrations.people import EmployeeRecordChecker, set_employee_record_checker
from app.main import app
from app.models.access_group import AccessGroup, UserGroupMembership
from app.models.audit_log import AuditLog
from app.models.module import ApplicationModule
from app.models.module_baseline import ModuleBaselineRole
from app.models.role import Permission, Role, RolePermission
from app.models.user import User, UserModuleRole
from app.services.authorization_service import AuthorizationService
from app.services.claims_service import build_claims
from app.services.entra_service import resolve_entra_user
from tests.conftest import auth_headers, internal_headers

TENANT = "tenant-1"
ISS = f"https://login.microsoftonline.com/{TENANT}/v2.0"
ADMIN = "/api/platform/admin"
MODULE, STANDARD, MANAGER = "field-ops", "FIELD_USER", "FIELD_MANAGER"
USER_PERMS, MANAGER_PERMS = frozenset({"field.use"}), frozenset({"field.use", "field.manage"})
NAMES = ["ana", "ben", "svc", "guest", "off", "ext", "twin1", "twin2"]
OID = {name: f"{i:08d}-0000-4000-8000-000000000000" for i, name in enumerate(NAMES, 1)}


def person(name, *, email=None, enabled=True, kind="Member", employee_id=None, title="Engineer"):
    email = email or f"{name}@dijital.example"
    return DirectoryUser(
        object_id=OID[name], display_name=name.title(), email=email, user_principal_name=email, job_title=title,
        department="Engineering", employee_id=employee_id, account_enabled=enabled, user_type=kind,
    )


DIRECTORY = [
    person("ana", employee_id="0107"),
    person("ben"),
    person("svc", email="svc-backup@dijital.example", title=None),  # a service account: in Entra, not in BambooHR
    person("guest", kind="Guest"),
    person("off", enabled=False),
    person("ext", email="someone@elsewhere.example"),
    person("twin1", email="shared@dijital.example"),
    DirectoryUser(object_id=OID["twin2"], display_name="Twin", email="other@dijital.example",
                  user_principal_name="shared@dijital.example"),
]


class People:
    def __init__(self, employees=None, workforce=None, down=False):
        self.employees = employees if employees is not None else [
            {"work_email": "ana@dijital.example", "employee_number": "0107", "employment_status": "Active"},
            {"work_email": "ben@dijital.example", "employee_number": "352", "employment_status": "Active"},
        ]
        self.workforce = workforce or []
        self.down = down

    def active_employees(self):
        if self.down:
            raise httpx.ConnectError("people-api down")
        return self.employees

    def active_workforce(self):
        if self.down:
            raise httpx.ConnectError("people-api down")
        return self.workforce


@pytest.fixture(autouse=True)
def _env(monkeypatch, db):
    monkeypatch.setenv("ENTRA_TENANT_ID", TENANT)
    monkeypatch.setenv("ENTRA_INTERNAL_EMAIL_DOMAINS", "dijital.example")
    monkeypatch.setenv("VIEW_AS_ENABLED", "true")
    get_settings.cache_clear()
    # A neutral application with an always-on standard role and a higher manager role (the same shape as
    # the real default application's standard and manager roles; module code stays out of platform tests).
    db.add_all([
        ApplicationModule(key=MODULE, name="Field Ops", description="", route="/field-ops", required_roles="ANY",
                          supports_client_scope=False),
        ModuleBaselineRole(module_key=MODULE, role=STANDARD, enabled=True),
        Permission(key="field.use", name="Use", description="", module_key=MODULE, category="x"),
        Permission(key="field.manage", name="Manage", description="", module_key=MODULE, category="x"),
        Role(module_key=MODULE, key=STANDARD, name="Field User", description="", is_system=False),
        Role(module_key=MODULE, key=MANAGER, name="Field Manager", description="", is_system=False),
    ])
    db.flush()
    perms = {p.key: p.id for p in db.query(Permission).filter(Permission.module_key == MODULE)}
    roles = {r.key: r.id for r in db.query(Role).filter(Role.module_key == MODULE)}
    db.add_all([
        RolePermission(role_id=roles[STANDARD], permission_id=perms["field.use"]),
        RolePermission(role_id=roles[MANAGER], permission_id=perms["field.use"]),
        RolePermission(role_id=roles[MANAGER], permission_id=perms["field.manage"]),
    ])
    db.commit()
    yield
    get_settings.cache_clear()
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_viewer, None)


@pytest.fixture()
def directory():
    provider = MockDirectoryProvider(
        users=list(DIRECTORY),
        photos={OID["ana"]: Photo(content=b"\xff\xd8jpeg", content_type="image/jpeg")},
        memberships={OID["ana"]: [
            DirectoryGroup(object_id="g-1", display_name="All Staff", group_type="Microsoft 365", direct=True),
            DirectoryGroup(object_id="g-2", display_name="Engineering", group_type="Security", direct=False),
        ]},
    )
    set_directory_provider(provider)
    return provider


@pytest.fixture()
def people():
    source = People()
    install(source)
    return source


def install(source):
    """A checker whose snapshot is already loaded, as in a running service (sign-in uses the cache)."""
    checker = EmployeeRecordChecker(source)
    checker.check(email="", employee_id=None)
    set_employee_record_checker(checker)
    return checker


@pytest.fixture()
def admin(api_client, two_tenant_world):
    return auth_headers(api_client, "test-super-admin")


def standard(db, user):
    db.expire_all()
    return AuthorizationService(db).effective_permissions(db.get(User, user.id), MODULE)


def add(api_client, admin, name):
    return api_client.post(f"{ADMIN}/users/from-directory", json={"entra_object_id": OID[name]}, headers=admin)


# --- search ------------------------------------------------------------------------------------


def test_search_returns_bounded_internal_members_with_hr_status(api_client, admin, directory, people):
    resp = api_client.get(f"{ADMIN}/directory/users", params={"q": "dijital"}, headers=admin)
    assert resp.status_code == 200, resp.text
    by_email = {r["email"]: r for r in resp.json()}
    assert "guest@dijital.example" not in by_email and "off@dijital.example" not in by_email
    assert "someone@elsewhere.example" not in by_email
    assert by_email["ana@dijital.example"]["employee_record"] == "MATCHED"
    assert by_email["ana@dijital.example"]["employee_number"] == "0107"
    assert by_email["svc-backup@dijital.example"]["employee_record"] == "NOT_FOUND"
    assert all(r["existing_user_id"] is None for r in resp.json())
    assert len(resp.json()) <= 15


def test_search_needs_a_query_and_the_manage_users_permission(api_client, admin, directory, people):
    assert api_client.get(f"{ADMIN}/directory/users", params={"q": "a"}, headers=admin).status_code == 422
    ta = auth_headers(api_client, "test-ta")
    assert api_client.get(f"{ADMIN}/directory/users", params={"q": "ana"}, headers=ta).status_code == 403
    assert api_client.get(f"{ADMIN}/directory/users", params={"q": "ana"}).status_code == 401


def test_search_marks_people_who_already_have_a_profile(api_client, admin, directory, people):
    created = add(api_client, admin, "ana").json()
    hits = api_client.get(f"{ADMIN}/directory/users", params={"q": "ana"}, headers=admin).json()
    assert hits[0]["existing_user_id"] == created["id"]


def test_an_unavailable_directory_is_a_503(api_client, admin, directory, people):
    directory.unavailable = True
    assert api_client.get(f"{ADMIN}/directory/users", params={"q": "ana"}, headers=admin).status_code == 503


# --- adding and verifying ----------------------------------------------------------------------


def test_adding_from_the_directory_populates_and_verifies_before_any_sign_in(api_client, db, admin, directory, people):
    resp = add(api_client, admin, "ana")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert (body["email"], body["full_name"], body["title"], body["employee_number"]) == (
        "ana@dijital.example", "Ana", "Engineer", "0107")
    assert body["entra_object_id"] == OID["ana"]
    assert body["directory_verified"] and body["verification_source"] == "DIRECTORY"
    assert body["employee_record"] == "MATCHED" and body["eligible_employee"] and not body["signed_in"]
    user = db.get(User, body["id"])
    assert user.last_login_at is None and user.platform_role == "PLATFORM_USER"
    assert standard(db, user) == USER_PERMS  # default access before the first sign-in
    assert list(build_claims(user, db)["module_roles"]) == [MODULE]  # and nothing else by default
    assert db.query(AuditLog).filter_by(action="user.directory_verified", entity_id=user.id).count() == 1


def test_adding_is_never_a_duplicate(api_client, db, admin, directory, people):
    first = add(api_client, admin, "ana").json()
    again = add(api_client, admin, "ana")
    assert again.status_code == 409 and again.json()["existing_user_id"] == first["id"]
    db.add(User(email="ben@dijital.example", full_name="Ben (manual)"))
    db.commit()
    by_email = add(api_client, admin, "ben")
    assert by_email.status_code == 409
    assert db.query(User).filter(User.email.in_(["ana@dijital.example", "ben@dijital.example"])).count() == 2


@pytest.mark.parametrize("name", ["guest", "off", "ext"])
def test_guests_disabled_and_external_accounts_cannot_be_added(api_client, admin, directory, people, name):
    assert add(api_client, admin, name).status_code == 400


def test_the_browser_cannot_supply_the_profile(api_client, admin, directory, people):
    resp = api_client.post(f"{ADMIN}/users/from-directory",
                           json={"entra_object_id": OID["ana"], "email": "boss@dijital.example", "full_name": "X"},
                           headers=admin)
    assert resp.status_code == 201 and resp.json()["email"] == "ana@dijital.example"


def test_verifying_a_manual_profile_keeps_every_assignment(api_client, db, admin, directory, people):
    user = User(email="ben@dijital.example", full_name="Ben", identity_provider="ENTRA", is_active=True)
    group = AccessGroup(key="crew", display_name="Crew")
    db.add_all([user, group])
    db.flush()
    db.add_all([UserModuleRole(user_id=user.id, module_key=MODULE, role=MANAGER, enabled=True),
                UserGroupMembership(user_id=user.id, access_group_id=group.id)])
    db.commit()
    resp = api_client.post(f"{ADMIN}/users/{user.id}/verify-directory", headers=admin)
    assert resp.status_code == 200, resp.text
    db.expire_all()
    roles = [(r.module_key, r.role, r.enabled) for r in db.query(UserModuleRole).filter_by(user_id=user.id)]
    assert roles == [(MODULE, MANAGER, True)]
    assert db.query(UserGroupMembership).filter_by(user_id=user.id).count() == 1
    assert standard(db, user) >= MANAGER_PERMS | USER_PERMS  # the higher role stays; the standard one is added


@pytest.mark.parametrize(
    ("email", "reason"),
    [
        ("nobody@dijital.example", "No directory account"),
        ("shared@dijital.example", "More than one"),
        ("guest@dijital.example", "not an enabled internal member"),
    ],
)
def test_verification_refuses_missing_ambiguous_and_guest_identities(api_client, db, admin, directory, people, email, reason):
    user = User(email=email, full_name="X", is_active=True)
    db.add(user)
    db.commit()
    resp = api_client.post(f"{ADMIN}/users/{user.id}/verify-directory", headers=admin)
    assert resp.status_code == 400 and reason in resp.json()["detail"]
    db.expire_all()
    assert db.get(User, user.id).internal_employee is False
    assert db.query(AuditLog).filter_by(action="user.directory_verification_failed", entity_id=user.id).count() == 1


def test_an_identity_already_bound_elsewhere_is_refused(api_client, db, admin, directory, people):
    db.add(User(email="old-ana@dijital.example", full_name="Old", entra_object_id=OID["ana"], identity_provider="ENTRA"))
    user = User(email="ana@dijital.example", full_name="Ana", is_active=True)
    db.add(user)
    db.commit()
    resp = api_client.post(f"{ADMIN}/users/{user.id}/verify-directory", headers=admin)
    assert resp.status_code == 400 and "already bound" in resp.json()["detail"]


# --- employee records --------------------------------------------------------------------------


def test_a_service_account_gets_an_identity_but_no_employee_access(api_client, db, admin, directory, people, two_tenant_world):
    body = add(api_client, admin, "svc").json()
    assert body["directory_verified"] and body["employee_record"] == "NOT_FOUND" and not body["eligible_employee"]
    user = db.get(User, body["id"])
    assert standard(db, user) == frozenset()
    resp = api_client.post(f"{ADMIN}/view-as", json={"target_user_id": user.id}, headers=admin)
    assert resp.status_code == 404 and "employee record" in resp.json()["detail"]
    # ... but its access can still be previewed.
    assert api_client.get(f"{ADMIN}/users/{user.id}/effective-access", headers=admin).status_code == 200


def test_a_service_account_signing_in_gets_no_employee_access(db, directory, people):
    user = User(email="svc-backup@dijital.example", full_name="Svc", is_active=True)
    db.add(user)
    db.commit()
    signed = resolve_entra_user(db, {"oid": OID["svc"], "email": "svc-backup@dijital.example", "name": "S",
                                     "tid": TENANT, "iss": ISS, "acct": 0})
    assert signed.internal_employee and signed.employee_record_status == "NOT_FOUND"
    assert standard(db, signed) == frozenset()


def test_a_sign_in_never_waits_for_the_hr_source(db, directory):
    """With no records loaded yet, the sign-in answers at once (UNKNOWN, nothing granted, nothing
    overwritten) and the records are loaded in the background for next time."""
    calls = []

    class Slow(People):
        def active_employees(self):
            calls.append("load")
            return super().active_employees()

    checker = EmployeeRecordChecker(Slow())
    set_employee_record_checker(checker)
    user = User(email="ana@dijital.example", full_name="Ana", is_active=True, employee_record_status="LEGACY",
                internal_employee=True, identity_provider="ENTRA", entra_object_id=OID["ana"])
    db.add(user)
    db.commit()
    signed = resolve_entra_user(db, {"oid": OID["ana"], "email": "ana@dijital.example", "name": "A",
                                         "tid": TENANT, "iss": ISS, "acct": 0})
    assert signed.employee_record_status == "LEGACY" and signed.last_login_at is not None
    for _ in range(50):
        if checker.cached() is not None:
            break
        time.sleep(0.02)
    assert checker.cached() is not None and calls == ["load"]


def test_an_unavailable_hr_source_never_grants(api_client, db, admin, directory):
    set_employee_record_checker(EmployeeRecordChecker(People(down=True)))
    body = add(api_client, admin, "ana").json()
    assert body["employee_record"] == "UNKNOWN" and not body["eligible_employee"]
    assert standard(db, db.get(User, body["id"])) == frozenset()


def test_a_transient_hr_failure_is_retried_once():
    class Flaky(People):
        calls = 0

        def active_employees(self):
            Flaky.calls += 1
            if Flaky.calls == 1:
                raise httpx.ReadTimeout("first load")
            return super().active_employees()

    checker = EmployeeRecordChecker(Flaky())
    assert checker.check(email="ana@dijital.example").status == "MATCHED" and Flaky.calls == 2


def test_employee_number_from_the_directory_matches_a_single_active_hr_entry(api_client, admin, directory):
    set_employee_record_checker(EmployeeRecordChecker(People(
        employees=[], workforce=[{"employee_number": "0107", "employment_status": "Active"}])))
    assert add(api_client, admin, "ana").json()["employee_record"] == "MATCHED"


def test_legacy_employees_keep_access_and_are_reported_not_revoked(api_client, db, admin, directory, two_tenant_world):
    install(People(employees=[
        {"work_email": "ana@dijital.example", "employee_number": "0107", "employment_status": "Active"}]))
    legacy = [User(email=f"{n}@dijital.example", full_name=n, is_active=True, internal_employee=True,
                   identity_provider="ENTRA", entra_object_id=OID[n], employee_record_status="LEGACY")
              for n in ("ana", "ben")]
    db.add_all(legacy)
    db.commit()
    resp = api_client.post(f"{ADMIN}/employee-records/reconcile", headers=admin)
    assert resp.status_code == 200, resp.text
    summary = resp.json()
    assert summary["matched"] == 1 and [e["email"] for e in summary["hr_exceptions"]] == ["ben@dijital.example"]
    db.expire_all()
    ana, ben = (db.get(User, u.id) for u in legacy)
    assert ana.employee_record_status == "MATCHED" and ana.employee_number == "0107"
    assert ben.employee_record_status == "LEGACY" and standard(db, ben) == USER_PERMS  # still has access
    # A later sign-in that does not find Ben in BambooHR does not take it away either.
    signed = resolve_entra_user(db, {"oid": OID["ben"], "email": "ben@dijital.example", "name": "B",
                                         "tid": TENANT, "iss": ISS, "acct": 0})
    assert signed.employee_record_status == "LEGACY" and standard(db, signed) == USER_PERMS


def test_reconciliation_changes_nothing_when_hr_is_unavailable(api_client, db, admin, directory):
    set_employee_record_checker(EmployeeRecordChecker(People(down=True)))
    user = User(email="ana@dijital.example", full_name="A", is_active=True, internal_employee=True,
                identity_provider="ENTRA", entra_object_id=OID["ana"], employee_record_status="LEGACY")
    db.add(user)
    db.commit()
    assert api_client.post(f"{ADMIN}/employee-records/reconcile", headers=admin).status_code == 503
    db.expire_all()
    assert db.get(User, user.id).employee_record_status == "LEGACY"


# --- pre-login View-as and the first sign-in ---------------------------------------------------


def test_pre_login_view_as_for_a_verified_employee(api_client, db, admin, directory, people):
    body = add(api_client, admin, "ana").json()
    started = api_client.post(f"{ADMIN}/view-as", json={"target_user_id": body["id"]}, headers=admin)
    assert started.status_code == 201, started.text
    token = started.json()["access_token"]
    view = {"Authorization": f"Bearer {token}"}
    assert api_client.get("/api/auth/me", headers=view).json()["email"] == "ana@dijital.example"
    assert MODULE in {m["key"] for m in api_client.get("/api/modules", headers=view).json()}
    assert api_client.get(f"{ADMIN}/users", headers=view).status_code == 403  # read-only, never a staff session
    assert db.get(User, body["id"]).last_login_at is None


def test_an_unverified_profile_cannot_be_viewed(api_client, db, admin, directory, people):
    user = User(email="ben@dijital.example", full_name="Ben", is_active=True)
    db.add(user)
    db.commit()
    resp = api_client.post(f"{ADMIN}/view-as", json={"target_user_id": user.id}, headers=admin)
    assert resp.status_code == 404 and "Verify with directory" in resp.json()["detail"]


def test_the_first_sign_in_links_to_the_provisioned_profile(api_client, db, admin, directory, people):
    body = add(api_client, admin, "ana").json()
    signed = resolve_entra_user(db, {"oid": OID["ana"], "email": "ana@dijital.example", "name": "A",
                                         "tid": TENANT, "iss": ISS, "acct": 0})
    assert signed.id == body["id"] and signed.last_login_at is not None
    assert db.query(User).filter_by(email="ana@dijital.example").count() == 1


# --- photos and Entra groups -------------------------------------------------------------------


def test_photos_are_served_from_the_backend_and_cached(api_client, db, admin, directory, people):
    body = add(api_client, admin, "ana").json()
    calls = []
    original = directory.photo
    directory.photo = lambda oid: calls.append(oid) or original(oid)
    first = api_client.get(f"{ADMIN}/users/{body['id']}/photo", headers=admin)
    assert first.status_code == 200 and first.content == b"\xff\xd8jpeg"
    assert first.headers["content-type"] == "image/jpeg" and "private" in first.headers["cache-control"]
    assert api_client.get(f"{ADMIN}/directory/users/{OID['ana']}/photo", headers=admin).status_code == 200
    assert calls == [OID["ana"]]  # the second read came from the cache
    assert "authorization" not in {k.lower() for k in first.headers}


def test_a_missing_photo_is_a_404_so_initials_are_shown(api_client, admin, directory, people):
    body = add(api_client, admin, "ben").json()
    assert api_client.get(f"{ADMIN}/users/{body['id']}/photo", headers=admin).status_code == 404


def test_my_photo_is_for_my_staff_session_only(api_client, db, admin, directory, people, two_tenant_world):
    user = db.get(User, two_tenant_world["super_admin"].id)
    user.entra_object_id = OID["ana"]
    db.commit()
    assert api_client.get("/api/auth/me/photo", headers=admin).status_code == 200
    assert api_client.get("/api/auth/me/photo").status_code == 401


def test_entra_groups_are_shown_read_only_and_grant_nothing(api_client, db, admin, directory, people):
    body = add(api_client, admin, "ana").json()
    before = build_claims(db.get(User, body["id"]), db)["module_roles"]
    groups = api_client.get(f"{ADMIN}/users/{body['id']}/entra-groups", headers=admin).json()
    assert [(g["display_name"], g["group_type"], g["membership"], g["dijione_mapping"]) for g in groups] == [
        ("All Staff", "Microsoft 365", "DIRECT", None), ("Engineering", "Security", "INHERITED", None)]
    db.expire_all()
    assert build_claims(db.get(User, body["id"]), db)["module_roles"] == before


def test_other_applications_stay_explicit_only(db, directory, people):
    for module_key in ("talent-flow", "birthday", "onsite"):
        assert db.get(ModuleBaselineRole, module_key) is None


# --- service-to-service operations ---------------------------------------------------------------


def test_the_internal_readiness_check_returns_flags_not_names(api_client, directory, people):
    resp = api_client.get("/api/platform/internal/directory/check", params={"email": "ana@dijital.example"},
                          headers=internal_headers())
    assert resp.status_code == 200
    assert resp.json() == {"directory_readable": True, "matches": 1, "internal_member": True, "employee_id_present": True,
                           "group_count": 2, "groups_readable": True, "photo_present": True,
                           "employee_record": "MATCHED", "employee_number_present": True}
    assert api_client.get("/api/platform/internal/directory/check", params={"email": "ana@dijital.example"}).status_code == 401
    directory.unavailable = True
    down = api_client.get("/api/platform/internal/directory/check", params={"email": "ana@dijital.example"},
                          headers=internal_headers()).json()
    assert down["directory_readable"] is False


def test_internal_reconciliation_is_audited_without_an_actor(api_client, db, directory, people):
    user = User(email="ana@dijital.example", full_name="A", is_active=True, internal_employee=True,
                identity_provider="ENTRA", entra_object_id=OID["ana"], employee_record_status="LEGACY")
    db.add(user)
    db.commit()
    assert api_client.post("/api/platform/internal/employee-records/reconcile").status_code == 401
    resp = api_client.post("/api/platform/internal/employee-records/reconcile", headers=internal_headers())
    assert resp.status_code == 200 and resp.json()["matched"] == 1
    db.expire_all()
    assert db.get(User, user.id).employee_record_status == "MATCHED"
    entry = db.query(AuditLog).filter_by(action="employee_records.reconciled").one()
    assert entry.actor_id is None


# --- the directory is read-only ----------------------------------------------------------------


def test_the_graph_provider_only_ever_sends_get_requests():
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.url.path.endswith("/$value"):
            return httpx.Response(404)
        if "memberOf" in request.url.path or "transitiveMemberOf" in request.url.path:
            return httpx.Response(200, json={"value": []})
        if request.url.path.endswith("/users"):
            return httpx.Response(200, json={"value": []})
        return httpx.Response(404)

    class Token:
        def get_token(self, _scope):
            return type("T", (), {"token": "t"})()

    provider = GraphDirectoryProvider(credential=Token(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    provider.search("ana")
    provider.search("0107")
    provider.get(OID["ana"])
    provider.find_by_email("ana@dijital.example")
    provider.photo(OID["ana"])
    provider.groups(OID["ana"])
    assert methods and set(methods) == {"GET"}
    source = inspect.getsource(directory_module)
    assert not re.search(r"\.(post|put|patch|delete)\(", source)
