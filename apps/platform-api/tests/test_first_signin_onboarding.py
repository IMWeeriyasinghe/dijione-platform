"""Automatic first-time Entra onboarding (DijiOne sign-in) and, separately, the mandatory
DijiAtWork employee baseline that still depends on a matching employee record."""

import threading
import time

import pytest
from sqlalchemy import select

from app.api.routes.auth import issue_user_session
from app.core.config import get_settings
from app.integrations.people import EmployeeRecord, EmployeeRecordChecker, set_employee_record_checker
from app.models.audit_log import AuditLog
from app.models.module_baseline import ModuleBaselineRole
from app.models.user import User, UserModuleRole
from app.models.user_module_client_scope import UserModuleClientScope
from app.services import entra_service
from app.services.authorization_service import AuthorizationService
from app.services.directory_service import DirectoryService
from app.services.entra_service import EntraLoginRefusedError, resolve_entra_user
from tests.conftest import internal_headers
from tests.test_atwork_registration import USER_PERMS, _register_module

TENANT = "tenant-1"
ISS = f"https://login.microsoftonline.com/{TENANT}/v2.0"


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setenv("ENTRA_TENANT_ID", TENANT)
    monkeypatch.setenv("ENTRA_INTERNAL_EMAIL_DOMAINS", "dijital.example")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def baseline(db):
    _register_module(db)
    db.add(ModuleBaselineRole(module_key="atwork", role="ATWORK_USER", enabled=True))
    db.commit()


def member(name="new", **over):
    return {"oid": f"oid-{name}", "email": f"{name}@dijital.example", "name": name, "tid": TENANT, "iss": ISS,
            "acct": 0, **over}


def audits(db, user, action):
    return db.execute(select(AuditLog).where(AuditLog.subject_user_id == user.id, AuditLog.action == action)).scalars().all()


class _Records(EmployeeRecordChecker):
    """Matches only the given addresses; everyone else is NOT_FOUND."""

    def __init__(self, matched=()):
        self.matched = set(matched)

    def check(self, *, email, employee_id=None, cached_only=False, wait_seconds=0.0):
        return EmployeeRecord("MATCHED" if email in self.matched else "NOT_FOUND", employee_number="0042")


# --- 1. Automatic DijiOne onboarding --------------------------------------------------------------

def test_genuinely_new_member_is_active_platform_user_with_audit_and_session(db, api_client):
    user = resolve_entra_user(db, member())
    assert user.is_active and user.platform_role == "PLATFORM_USER" and user.last_login_at is not None
    created, activated = audits(db, user, "user.created"), audits(db, user, "user.activated")
    assert len(created) == 1 and '"ENTRA_SIGN_IN"' in created[0].new_state
    assert len(activated) == 1 and "AUTOMATIC_FIRST_SIGN_IN" in activated[0].event_metadata
    token = issue_user_session(user, db)
    me = api_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["platform_role"] == "PLATFORM_USER"


def test_repeat_sign_in_is_idempotent(db):
    first = resolve_entra_user(db, member())
    again = resolve_entra_user(db, member())
    assert first.id == again.id
    assert db.query(User).filter_by(entra_object_id="oid-new").count() == 1
    assert len(audits(db, first, "user.created")) == 1 and len(audits(db, first, "user.activated")) == 1


def test_concurrent_first_sign_in_of_the_same_identity_creates_one_account(db, monkeypatch):
    """Both requests read 'no such user' before either inserted: the unique object id decides and
    the loser reuses the winner's row, with no duplicate account or audit."""
    winner = resolve_entra_user(db, member())
    real_execute = db.execute
    calls = {"n": 0}

    def stale_first_lookup(stmt, *a, **k):
        calls["n"] += 1
        result = real_execute(stmt, *a, **k)
        if calls["n"] <= 2:  # the oid and email lookups, as seen by the request that lost the race
            class _Empty:
                def scalars(self):
                    return self

                def first(self):
                    return None

                def all(self):
                    return []
            return _Empty()
        return result

    monkeypatch.setattr(db, "execute", stale_first_lookup)
    loser = resolve_entra_user(db, member())
    monkeypatch.undo()
    assert loser.id == winner.id
    assert db.query(User).filter_by(entra_object_id="oid-new").count() == 1
    assert len(audits(db, winner, "user.created")) == 1 and len(audits(db, winner, "user.activated")) == 1


def test_existing_active_user_is_unchanged(db):
    user = User(email="emp@dijital.example", full_name="E", is_active=True, entra_object_id="oid-emp",
                identity_provider="ENTRA")
    db.add(user)
    db.commit()
    assert resolve_entra_user(db, member("emp")).id == user.id
    assert audits(db, user, "user.created") == [] and audits(db, user, "user.activated") == []


def test_inactive_row_from_the_old_policy_without_provenance_stays_inactive(db):
    """The account created by the earlier policy has no provenance audit: its origin cannot be
    established, so it is never activated automatically (fail closed)."""
    old = User(email="old@dijital.example", full_name="O", is_active=False, entra_object_id="oid-old",
               identity_provider="ENTRA", platform_role="PLATFORM_USER")
    db.add(old)
    db.commit()
    with pytest.raises(EntraLoginRefusedError):
        resolve_entra_user(db, member("old"))
    db.expire_all()
    assert db.get(User, old.id).is_active is False


def test_pending_self_signin_row_with_provenance_is_activated(db):
    """A row created by a sign-in while the identity was not yet proven internal (provenance audit
    present, nobody decided on it) is activated once a proven Member signs in."""
    with pytest.raises(EntraLoginRefusedError):
        resolve_entra_user(db, member("p", acct=None))
    user = resolve_entra_user(db, member("p"))
    assert user.is_active
    assert len(audits(db, user, "user.activated")) == 1


def test_administrator_decision_is_never_overridden(db):
    with pytest.raises(EntraLoginRefusedError):
        resolve_entra_user(db, member("d", acct=None))
    user = db.query(User).filter_by(entra_object_id="oid-d").one()
    db.add(AuditLog(actor_id=None, action="user.deactivated", entity_type="User", entity_id=user.id,
                    subject_user_id=user.id, previous_state="", new_state="", event_metadata=""))
    db.commit()
    with pytest.raises(EntraLoginRefusedError):
        resolve_entra_user(db, member("d"))


def test_deactivated_user_who_signed_in_before_is_refused(db):
    user = resolve_entra_user(db, member("x"))
    user.is_active = False
    db.commit()
    with pytest.raises(EntraLoginRefusedError):
        resolve_entra_user(db, member("x"))


@pytest.mark.parametrize(
    "over",
    [
        {"acct": 1},  # Guest
        {"acct": None},  # optional claim missing: membership not proven
        {"email": "g_other.example#EXT#@dijital.example"},  # B2B guest UPN
        {"tid": "another-tenant"},
        {"idp": "https://sts.windows.net/another-tenant/"},  # foreign identity provider
        {"idp": None, "iss": "https://login.microsoftonline.com/another-tenant/v2.0"},  # no idp: issuer decides
        {"email": "someone@other.example"},  # domain not ours
    ],
)
def test_unproven_identities_are_created_inactive_and_refused(db, over):
    with pytest.raises(EntraLoginRefusedError):
        resolve_entra_user(db, member("u", **over))
    user = db.query(User).filter_by(entra_object_id="oid-u").one()
    assert user.is_active is False and user.internal_employee is False


def test_idp_absent_with_our_issuer_is_accepted(db):
    assert resolve_entra_user(db, member("i", idp=None)).is_active


def test_onboarding_grants_nothing_else(db, baseline):
    set_employee_record_checker(_Records())  # not an employee: no default access either
    user = resolve_entra_user(db, member())
    assert user.platform_role == "PLATFORM_USER"
    assert db.query(UserModuleRole).filter_by(user_id=user.id).count() == 0
    assert db.query(UserModuleClientScope).count() == 0
    assert AuthorizationService(db).effective_module_roles(user) == {}
    assert AuthorizationService(db).platform_permissions(user) == frozenset()


# --- 2. Mandatory DijiAtWork baseline (separate from sign-in) ------------------------------------

def test_matched_new_employee_gets_atwork_and_nothing_else(db, baseline, api_client):
    set_employee_record_checker(_Records({"new@dijital.example"}))
    user = resolve_entra_user(db, member())
    assert user.employee_record_status == "MATCHED"
    roles = AuthorizationService(db).effective_module_roles(user)
    assert set(roles) == {"atwork"} and [g.role for g in roles["atwork"]] == ["ATWORK_USER"]
    assert AuthorizationService(db).effective_permissions(user, "atwork") == USER_PERMS
    headers = {"Authorization": f"Bearer {issue_user_session(user, db)}"}
    assert "atwork" in {m["key"] for m in api_client.get("/api/modules", headers=headers).json()}  # DijiOne Home
    live = api_client.get(f"/api/platform/internal/users/{user.id}/modules/atwork/permissions",
                          headers=internal_headers())  # what atwork-api checks on every request
    assert live.status_code == 200 and set(live.json()["permissions"]) == USER_PERMS


def test_internal_service_account_signs_in_without_attendance_access(db, baseline):
    set_employee_record_checker(_Records())
    svc = resolve_entra_user(db, member("svc"))
    assert svc.is_active and svc.employee_record_status == "NOT_FOUND"
    assert AuthorizationService(db).effective_permissions(svc, "atwork") == frozenset()


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
    user = resolve_entra_user(db, member())
    assert user.employee_record_status == "MATCHED"
    assert AuthorizationService(db).effective_permissions(user, "atwork") == USER_PERMS
    assert checker.source.calls == 1


def test_slow_hr_source_never_blocks_sign_in_and_reconciliation_completes_entitlement(db, baseline, monkeypatch):
    monkeypatch.setattr(entra_service, "FIRST_SIGNIN_HR_WAIT_SECONDS", 0.2)
    checker = _SlowSnapshot(1.0, ["new@dijital.example"])
    set_employee_record_checker(checker)
    started = time.monotonic()
    user = resolve_entra_user(db, member())
    assert time.monotonic() - started < 0.9  # bounded wait, the load continues in the background
    assert user.is_active and user.employee_record_status == "UNKNOWN"
    assert AuthorizationService(db).effective_permissions(user, "atwork") == frozenset()  # not yet eligible
    for t in threading.enumerate():
        if t.name == "employee-records-warm":
            t.join(3)
    assert checker.source.calls == 1  # the sign-in started one background load, never more
    DirectoryService(db).reconcile_employee_records(actor=None)  # no manual assignment
    db.refresh(user)
    assert user.employee_record_status == "MATCHED"
    assert AuthorizationService(db).effective_permissions(user, "atwork") == USER_PERMS
