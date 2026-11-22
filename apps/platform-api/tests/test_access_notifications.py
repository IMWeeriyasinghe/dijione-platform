"""Access-change email notifications: queued with the change, only for real effective-access
changes, one per affected person, never for rolled-back changes, never able to break the change."""

import pytest
from mail_client_py import MailOutcome, MailResult, MailTransport
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.permissions import BASELINE_UNVERIFIED_PERMISSIONS, BIRTHDAY_ROLES
from app.models.access_group import AccessGroup, GroupModuleRole, UserGroupMembership
from app.models.email_notification import (
    EmailOutbox,
    EmailTestRecipient,
    NotificationEventSetting,
    OutboxStatus,
    UserAccessSnapshot,
)
from app.models.module import ApplicationModule
from app.models.module_baseline import ModuleBaselineRole
from app.models.user import User, UserModuleRole
from app.services import access_notifications, email_dispatcher
from app.services.access_notifications import (
    EVENT_DEACTIVATED,
    EVENT_GRANTED,
    EVENT_REVOKED,
    EVENT_ROLE_UPDATED,
    EVENT_WELCOME,
)
from app.services.email_dispatcher import dispatch_due, set_transport_override
from app.services.entra_service import resolve_entra_user
from tests.conftest import auth_headers, make_eligible

TALENT = "talent-flow"
ALL_CLIENTS = {"all_clients": True}
TENANT = "tenant-1"
ISS = f"https://login.microsoftonline.com/{TENANT}/v2.0"


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setenv("ENTRA_TENANT_ID", TENANT)
    monkeypatch.setenv("ENTRA_INTERNAL_EMAIL_DOMAINS", "dijital.example")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    set_transport_override(None)


def rows(db, user_id=None):
    db.expire_all()
    stmt = select(EmailOutbox).order_by(EmailOutbox.id)
    if user_id is not None:
        stmt = stmt.where(EmailOutbox.recipient_user_id == user_id)
    return list(db.execute(stmt).scalars())


def live(db, user_id=None):
    return [r for r in rows(db, user_id) if r.status != OutboxStatus.SUPERSEDED]


def clear_outbox(db):
    db.execute(delete(EmailOutbox))
    db.commit()


@pytest.fixture()
def world(db, two_tenant_world):
    """Everyone in two_tenant_world was created (and welcomed) by the fixture; start clean."""
    clear_outbox(db)
    return two_tenant_world


@pytest.fixture()
def default_app(db, monkeypatch):
    """A neutral default application: every active person gets BIRTHDAY_USER by baseline, but
    only one permission until their employee record is matched (as an opt-in default app works)."""
    role = next(r for r in BIRTHDAY_ROLES if r.key == "BIRTHDAY_USER")
    monkeypatch.setitem(BASELINE_UNVERIFIED_PERMISSIONS, "birthday", frozenset(sorted(role.permissions)[:1]))
    if db.execute(select(ApplicationModule).where(ApplicationModule.key == "birthday")).scalar_one_or_none() is None:
        db.add(ApplicationModule(key="birthday", name="Birthday", description="Test default app", icon="Gift",
                                 route="/birthday", status="ACTIVE", enabled=True, display_order=9,
                                 required_roles="ANY", supports_client_scope=False))
    db.add(ModuleBaselineRole(module_key="birthday", role="BIRTHDAY_USER", enabled=True))
    db.commit()


def default_app_name(db):
    return db.execute(
        select(ApplicationModule.name).where(ApplicationModule.key == "birthday")).scalar_one()


def app_name(db, key):
    """The registry display name (the source of single-application subjects); key if unregistered."""
    return db.execute(select(ApplicationModule.name).where(ApplicationModule.key == key)).scalar_one_or_none() or key


def new_person(db, name="person", **extra):
    user = User(email=f"{name}@dijital.example", full_name=name, **extra)
    db.add(user)
    db.commit()
    return user


# --- first access and default applications ------------------------------------------------------


def test_new_user_with_an_application_gets_one_welcome(db, world):
    user = User(email="newbie@example.com", full_name="Newbie")
    db.add(user)
    db.flush()
    db.add(UserModuleRole(user_id=user.id, module_key=TALENT, role="TA_MEMBER"))
    db.commit()
    [row] = rows(db, user.id)
    assert row.event_type == EVENT_WELCOME
    assert row.subject == "[DijiOne] | Access Available"
    assert row.template_data["apps"] == [TALENT]
    assert row.status == OutboxStatus.PENDING


def test_first_sign_in_with_a_default_app_sends_one_email_only(db, default_app):
    claims = {"oid": "oid-emp", "email": "emp@dijital.example", "name": "Emp", "tid": TENANT, "iss": ISS, "acct": 0}
    user = resolve_entra_user(db, claims)
    resolve_entra_user(db, claims)  # signing in again changes nothing
    [row] = live(db, user.id)
    assert row.event_type == EVENT_WELCOME
    assert row.template_data["apps"] == [default_app_name(db)]


def test_default_access_growing_with_eligibility_is_not_a_second_email(db, default_app):
    user = new_person(db, "emp")  # active platform user: default access only
    assert [r.event_type for r in live(db, user.id)] == [EVENT_WELCOME]
    make_eligible(user)  # matched employee record: the rest of the role's permissions arrive
    db.commit()
    assert [r.event_type for r in live(db, user.id)] == [EVENT_WELCOME]


def test_existing_people_get_a_silent_baseline(db, world):
    db.execute(delete(UserAccessSnapshot))
    db.commit()
    ta = world["ta_user"]
    db.add(UserModuleRole(user_id=ta.id, module_key="birthday", role="BIRTHDAY_USER"))
    db.commit()
    assert rows(db) == []
    assert db.get(UserAccessSnapshot, ta.id) is not None


def test_backfill_records_everyone_without_emails(db, world):
    db.execute(delete(UserAccessSnapshot))
    db.commit()
    added = access_notifications.backfill_snapshots(db)
    assert added == db.execute(select(User)).scalars().all().__len__()
    assert rows(db) == []
    assert access_notifications.backfill_snapshots(db) == 0


# --- grants, revocations, role changes -------------------------------------------------------------


def test_grant_revoke_and_role_change_through_the_admin_api(db, world, api_client, monkeypatch):
    headers = auth_headers(api_client, "test-super-admin")
    ta = world["ta_user"]

    resp = api_client.put(
                          f"/api/platform/admin/users/{ta.id}/modules/birthday",
                          json={"role": "BIRTHDAY_USER", "client_scope": ALL_CLIENTS},
                          headers=headers)
    assert resp.status_code == 200, resp.text
    [granted] = live(db, ta.id)
    assert (granted.event_type, granted.subject) == (EVENT_GRANTED, f"[{app_name(db, 'birthday')}] | Access Granted")
    assert granted.application_key == "birthday"
    assert granted.template_data["granted"] == [app_name(db, "birthday")]

    dispatch_due()  # sent, so the next change is a separate email
    resp = api_client.put(
                          f"/api/platform/admin/users/{ta.id}/modules/{TALENT}",
                          json={"role": "TA_MANAGER", "client_scope": ALL_CLIENTS},
                          headers=headers)
    assert resp.status_code == 200, resp.text
    updated = live(db, ta.id)[-1]
    assert (updated.event_type, updated.subject) == (EVENT_ROLE_UPDATED, f"[{app_name(db, TALENT)}] | Role Updated")

    dispatch_due()
    resp = api_client.delete(f"/api/platform/admin/users/{ta.id}/modules/birthday", headers=headers)
    assert resp.status_code == 200, resp.text
    revoked = live(db, ta.id)[-1]
    assert (revoked.event_type, revoked.template_data["revoked"]) == (EVENT_REVOKED, [app_name(db, "birthday")])
    assert len(live(db, ta.id)) == 3


def test_a_change_that_does_not_alter_effective_access_sends_nothing(db, world):
    ta = world["ta_user"]
    role = db.execute(select(UserModuleRole).where(UserModuleRole.user_id == ta.id)).scalar_one()
    role.client_id = role.client_id  # touched, unchanged
    db.add(UserModuleRole(user_id=ta.id, module_key="unknown-module-without-permissions", role="NOBODY"))
    db.commit()
    assert rows(db, ta.id) == []


def test_deactivation_is_one_email_not_a_revocation_per_application(db, world, api_client):
    ta = world["ta_user"]
    resp = api_client.patch(f"/api/platform/admin/users/{ta.id}/status", json={"is_active": False},
                            headers=auth_headers(api_client, "test-super-admin"))
    assert resp.status_code == 200, resp.text
    [row] = live(db, ta.id)
    assert (row.event_type, row.subject) == (EVENT_DEACTIVATED, "[DijiOne] | Account Deactivated")


# --- groups ---------------------------------------------------------------------------------------


def test_group_assignment_emails_only_people_whose_access_changes(db, world):
    ta, cs, abc = world["ta_user"], world["cs_user"], world["abc_user"]
    db.add(UserModuleRole(user_id=cs.id, module_key="birthday", role="BIRTHDAY_USER"))
    db.commit()
    clear_outbox(db)

    group = AccessGroup(key="hr", display_name="HR", status="ACTIVE")
    db.add(group)
    db.flush()
    db.add_all([UserGroupMembership(user_id=u.id, access_group_id=group.id) for u in (ta, cs, abc)])
    db.commit()
    assert rows(db) == []  # a group with no applications changes nobody's access

    db.add(GroupModuleRole(access_group_id=group.id, module_key="birthday", role="BIRTHDAY_USER"))
    db.commit()
    recipients = sorted(r.recipient_user_id for r in live(db))
    assert recipients == sorted([ta.id, abc.id])  # cs already had exactly this access
    assert {r.event_type for r in live(db)} == {EVENT_GRANTED}


def test_group_membership_removal_revokes(db, world):
    ta = world["ta_user"]
    group = AccessGroup(key="hr2", display_name="HR", status="ACTIVE")
    db.add(group)
    db.flush()
    db.add(GroupModuleRole(access_group_id=group.id, module_key="birthday", role="BIRTHDAY_USER"))
    membership = UserGroupMembership(user_id=ta.id, access_group_id=group.id)
    db.add(membership)
    db.commit()
    dispatch_due()
    db.delete(membership)
    db.commit()
    assert live(db, ta.id)[-1].event_type == EVENT_REVOKED


# --- transactional guarantees ---------------------------------------------------------------------


def test_a_rolled_back_change_queues_nothing(db, world):
    ta = world["ta_user"]
    before = dict(db.get(UserAccessSnapshot, ta.id).snapshot)
    db.add(UserModuleRole(user_id=ta.id, module_key="birthday", role="BIRTHDAY_USER"))
    db.flush()
    db.rollback()
    db.add(User(email="unrelated@example.com", full_name="Unrelated"))  # a later, unrelated commit
    db.commit()
    assert rows(db, ta.id) == []
    assert db.get(UserAccessSnapshot, ta.id).snapshot == before


def test_a_notification_failure_never_breaks_the_access_change(db, world, monkeypatch):
    ta = world["ta_user"]

    def boom(*_a, **_k):
        raise RuntimeError("template store down")

    monkeypatch.setattr(access_notifications, "process_pending", boom)
    db.add(UserModuleRole(user_id=ta.id, module_key="birthday", role="BIRTHDAY_USER"))
    db.commit()  # must not raise
    db.expire_all()
    assert db.execute(
        select(UserModuleRole).where(UserModuleRole.user_id == ta.id, UserModuleRole.module_key == "birthday")
    ).scalar_one()
    assert rows(db, ta.id) == []


def test_sign_in_survives_a_notification_failure(db, default_app, monkeypatch):
    monkeypatch.setattr(access_notifications, "process_pending",
                        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("x")))
    claims = {"oid": "oid-s", "email": "s@dijital.example", "name": "S", "tid": TENANT, "iss": ISS, "acct": 0}
    assert resolve_entra_user(db, claims).id is not None


def test_a_quick_follow_up_change_is_folded_and_an_undone_change_sends_nothing(db, world):
    ta = world["ta_user"]
    role = UserModuleRole(user_id=ta.id, module_key="birthday", role="BIRTHDAY_USER")
    db.add(role)
    db.commit()
    db.delete(role)
    db.commit()
    assert live(db, ta.id) == []
    assert [r.status for r in rows(db, ta.id)] == [OutboxStatus.SUPERSEDED]


def test_folded_change_describes_the_net_result(db, world):
    ta = world["ta_user"]
    db.add(UserModuleRole(user_id=ta.id, module_key="birthday", role="BIRTHDAY_USER"))
    db.commit()
    talent = db.execute(select(UserModuleRole).where(UserModuleRole.user_id == ta.id,
                                                     UserModuleRole.module_key == TALENT)).scalar_one()
    db.delete(talent)
    db.commit()
    [row] = live(db, ta.id)
    assert row.template_data["granted"] == ["birthday"]
    assert row.template_data["revoked"] == [TALENT]


def test_switched_off_event_queues_nothing(db, world):
    db.add(NotificationEventSetting(event_type=EVENT_GRANTED, enabled=False))
    db.commit()
    db.add(UserModuleRole(user_id=world["ta_user"].id, module_key="birthday", role="BIRTHDAY_USER"))
    db.commit()
    assert rows(db) == []


def test_master_switch_off_keeps_snapshots_without_emails(db, world, monkeypatch):
    monkeypatch.setenv("ACCESS_NOTIFICATIONS_ENABLED", "false")
    get_settings.cache_clear()
    ta = world["ta_user"]
    db.add(UserModuleRole(user_id=ta.id, module_key="birthday", role="BIRTHDAY_USER"))
    db.commit()
    assert rows(db) == []


# --- dispatcher --------------------------------------------------------------------------------------


class RecordingTransport(MailTransport):
    def __init__(self, outcome=MailOutcome.SUBMITTED):
        self.outcome, self.sent = outcome, []

    def send(self, *, to, subject, body, correlation_id, content_type="Text"):
        self.sent.append((to, subject, body, content_type))
        ok = self.outcome is MailOutcome.SUBMITTED
        return MailResult(correlation_id=correlation_id, outcome=self.outcome, sent=ok,
                          error=None if ok else "Graph sendMail returned 503")


def _graph(monkeypatch, policy, env="dev"):
    monkeypatch.setenv("MAIL_TRANSPORT", "graph")
    monkeypatch.setenv("MAIL_POLICY", policy)
    monkeypatch.setenv("APP_ENV", env)
    get_settings.cache_clear()


def _grant(db, world, module="birthday", role="BIRTHDAY_USER"):
    user = world["ta_user"]
    db.add(UserModuleRole(user_id=user.id, module_key=module, role=role))
    db.commit()
    return user


def test_null_transport_simulates(db, world):
    _grant(db, world)
    assert dispatch_due() == {OutboxStatus.SIMULATED: 1}
    [row] = rows(db)
    assert row.transport_outcome == "SIMULATED" and row.attempts == 1 and row.completed_at


def test_submitted_is_recorded_with_html_body(db, world, monkeypatch):
    _graph(monkeypatch, "production", env="prod")
    transport = RecordingTransport()
    set_transport_override(transport)
    _grant(db, world)
    assert dispatch_due() == {OutboxStatus.SUBMITTED: 1}
    to, subject, body, content_type = transport.sent[0]
    assert (to, subject, content_type) == ("ta-user@example.com", f"[{app_name(db, 'birthday')}] | Access Granted", "HTML")
    assert "birthday" in body and "Access granted" in body


def test_dev_allowlist_blocks_unlisted_recipients_then_admin_retry_sends(db, world, monkeypatch):
    _graph(monkeypatch, "internal_allowlist")
    transport = RecordingTransport()
    set_transport_override(transport)
    _grant(db, world)
    assert dispatch_due() == {OutboxStatus.BLOCKED: 1}
    assert transport.sent == []

    db.add(EmailTestRecipient(address="ta-user@example.com"))
    db.commit()
    [row] = rows(db)
    from app.services.email_admin_service import EmailAdminService

    EmailAdminService(db).retry(actor=world["super_admin"], outbox_id=row.id)
    assert dispatch_due() == {OutboxStatus.SUBMITTED: 1}


def test_production_policy_is_refused_outside_production(db, world, monkeypatch):
    _graph(monkeypatch, "production", env="uat")
    transport = RecordingTransport()
    set_transport_override(transport)
    _grant(db, world)
    assert dispatch_due() == {OutboxStatus.DISABLED: 1}
    assert transport.sent == []


def test_disabled_policy_is_the_default_for_graph(db, world, monkeypatch):
    monkeypatch.setenv("MAIL_TRANSPORT", "graph")
    monkeypatch.delenv("MAIL_POLICY", raising=False)
    get_settings.cache_clear()
    set_transport_override(RecordingTransport())
    _grant(db, world)
    assert dispatch_due() == {OutboxStatus.DISABLED: 1}


def test_graph_failures_retry_with_backoff_then_fail(db, world, monkeypatch):
    _graph(monkeypatch, "production", env="prod")
    monkeypatch.setenv("EMAIL_MAX_ATTEMPTS", "3")
    get_settings.cache_clear()
    set_transport_override(RecordingTransport(MailOutcome.FAILED))
    _grant(db, world)
    assert dispatch_due() == {OutboxStatus.RETRY: 1}
    [row] = rows(db)
    assert row.attempts == 1 and "503" in row.last_error
    assert dispatch_due() == {}  # not due yet: backoff
    for _ in range(2):
        row.not_before = row.created_at
        db.commit()
        dispatch_due()
        row = rows(db)[0]
    assert (row.status, row.attempts) == (OutboxStatus.FAILED, 3)


def test_transport_exception_is_a_retryable_failure(db, world, monkeypatch):
    class Exploding(MailTransport):
        def send(self, **_k):
            raise RuntimeError("socket closed")

    set_transport_override(Exploding())
    _grant(db, world)
    assert dispatch_due() == {OutboxStatus.RETRY: 1}


def test_event_switched_off_before_sending_is_skipped(db, world):
    _grant(db, world)
    db.add(NotificationEventSetting(event_type=EVENT_GRANTED, enabled=False))
    db.commit()
    assert dispatch_due() == {OutboxStatus.SKIPPED: 1}


def test_a_claimed_row_is_not_sent_twice_and_stale_claims_are_released(db, world):
    _grant(db, world)
    [row] = rows(db)
    assert email_dispatcher._claim(db, row.id) is True
    assert email_dispatcher._claim(db, row.id) is False  # another replica
    assert dispatch_due() == {}
    row = rows(db)[0]
    row.claimed_at = row.created_at.replace(year=row.created_at.year - 1)
    db.commit()
    assert dispatch_due() == {OutboxStatus.SIMULATED: 1}


def test_names_from_data_are_escaped_in_the_email(db, world, monkeypatch):
    _graph(monkeypatch, "production", env="prod")
    transport = RecordingTransport()
    set_transport_override(transport)
    db.add(ApplicationModule(key="evil", name="<script>x</script>", description="", route="/evil", enabled=True))
    db.commit()
    _grant(db, world, module="evil", role="BIRTHDAY_USER")
    db.add(UserModuleRole(user_id=world["ta_user"].id, module_key="birthday", role="BIRTHDAY_USER"))
    db.commit()
    dispatch_due()
    body = transport.sent[0][2]
    assert "<script>" not in body


# --- administration -------------------------------------------------------------------------------


ADMIN = "/api/platform/admin/notifications"


def test_admin_can_filter_inspect_and_retry(db, world, api_client, monkeypatch):
    headers = auth_headers(api_client, "test-super-admin")
    _grant(db, world)
    _graph(monkeypatch, "internal_allowlist")
    set_transport_override(RecordingTransport())
    assert api_client.post(f"{ADMIN}/dispatch", headers=headers).json() == {"processed": {"BLOCKED": 1}}

    listing = api_client.get(f"{ADMIN}/outbox", params={"status": "BLOCKED", "recipient": "ta-user"},
                             headers=headers).json()
    assert listing["total"] == 1 and listing["items"][0]["can_retry"] is True
    item_id = listing["items"][0]["id"]
    detail = api_client.get(f"{ADMIN}/outbox/{item_id}", headers=headers).json()
    assert detail["subject"] == f"[{app_name(db, 'birthday')}] | Access Granted" and "last_error" in detail
    assert api_client.get(f"{ADMIN}/outbox", params={"event_type": EVENT_REVOKED}, headers=headers).json()["total"] == 0

    resp = api_client.post(f"{ADMIN}/test-recipients", json={"address": "TA-user@example.com"}, headers=headers)
    assert resp.status_code == 201 and resp.json()[0]["address"] == "ta-user@example.com"
    assert api_client.post(f"{ADMIN}/test-recipients", json={"address": "not-an-address"},
                           headers=headers).status_code == 422
    assert api_client.post(f"{ADMIN}/outbox/{item_id}/retry", headers=headers).status_code == 200
    assert api_client.post(f"{ADMIN}/dispatch", headers=headers).json() == {"processed": {"SUBMITTED": 1}}
    assert api_client.post(f"{ADMIN}/outbox/{item_id}/retry", headers=headers).status_code == 409

    summary = api_client.get(f"{ADMIN}/summary", headers=headers).json()
    assert summary["effective_policy"] == "internal_allowlist" and summary["counts"]["SUBMITTED"] == 1


def test_admin_can_switch_events(db, world, api_client):
    headers = auth_headers(api_client, "test-super-admin")
    events = api_client.put(f"{ADMIN}/events/{EVENT_GRANTED}", json={"enabled": False}, headers=headers).json()
    assert {e["event_type"]: e["enabled"] for e in events}[EVENT_GRANTED] is False
    assert api_client.put(f"{ADMIN}/events/nope", json={"enabled": False}, headers=headers).status_code == 404


@pytest.mark.parametrize("persona", ["test-ta", "test-abc-client"])
def test_ordinary_users_cannot_administer_email(db, world, api_client, persona):
    headers = auth_headers(api_client, persona)
    assert api_client.get(f"{ADMIN}/outbox", headers=headers).status_code == 403
    assert api_client.post(f"{ADMIN}/dispatch", headers=headers).status_code == 403
    assert api_client.post(f"{ADMIN}/test-recipients", json={"address": "a@b.co"}, headers=headers).status_code == 403


def test_view_as_session_cannot_administer_email_or_change_access(db, world, api_client, monkeypatch):
    monkeypatch.setenv("VIEW_AS_ENABLED", "true")
    get_settings.cache_clear()
    ta = make_eligible(db.get(User, world["ta_user"].id))
    db.commit()
    clear_outbox(db)
    started = api_client.post("/api/platform/admin/view-as", json={"target_user_id": ta.id},
                              headers=auth_headers(api_client, "test-super-admin"))
    assert started.status_code == 201, started.text
    view_as = {"Authorization": f"Bearer {started.json()['access_token']}"}
    assert api_client.get(f"{ADMIN}/outbox", headers=view_as).status_code == 403
    assert api_client.post(f"{ADMIN}/outbox/1/retry", headers=view_as).status_code == 403
    assert api_client.put(
                          f"/api/platform/admin/users/{ta.id}/modules/birthday",
                          json={"role": "BIRTHDAY_USER", "client_scope": ALL_CLIENTS},
                          headers=view_as).status_code == 403
    assert rows(db) == []


def test_out_of_band_catalog_change_is_absorbed_silently_and_never_reported_later(db, world):
    """A release migration that grows a role must not appear in the next unrelated email."""
    from app.models.role import Permission, Role, RolePermission

    ta = world["ta_user"]
    role = db.execute(select(Role).where(Role.key == "TA_MEMBER")).scalar_one()
    # Simulate a data migration: raw SQL only, so the ORM listener never sees it.
    db.execute(Permission.__table__.insert().values(key="talent.release_added", name="Release added",
                                                    description="", module_key=TALENT,
                                                    created_at=role.created_at, updated_at=role.updated_at))
    perm_id = db.execute(select(Permission.id).where(Permission.key == "talent.release_added")).scalar_one()
    db.execute(RolePermission.__table__.insert().values(role_id=role.id, permission_id=perm_id))
    db.commit()
    assert rows(db) == []

    assert access_notifications.rebaseline_snapshots(db) >= 1
    assert rows(db) == []
    db.add(UserModuleRole(user_id=ta.id, module_key="birthday", role="BIRTHDAY_USER"))
    db.commit()
    [row] = live(db, ta.id)
    assert row.event_type == EVENT_GRANTED
    assert row.template_data["changed"] == []  # the release change is not reported
    assert access_notifications.rebaseline_snapshots(db) == 0  # idempotent


# --- platform-wide changes are silent (M-1) -----------------------------------------------------


def _birthday_module(db):
    module = db.execute(select(ApplicationModule).where(ApplicationModule.key == "birthday")).scalar_one_or_none()
    if module is None:
        module = ApplicationModule(key="birthday", name="DIJI Birthday", description="", route="/birthday",
                                   enabled=True)
        db.add(module)
        db.commit()
    return module


def _set_talent_role(db, user, role):
    row = db.execute(select(UserModuleRole).where(UserModuleRole.user_id == user.id,
                                                  UserModuleRole.module_key == TALENT)).scalar_one()
    row.role = role


def _holder(db, world):
    """ta_user holds birthday; their own grant email is already sent."""
    _birthday_module(db)
    ta = _grant(db, world)
    dispatch_due()
    clear_outbox(db)
    return ta


def test_disabling_and_re_enabling_an_application_emails_nobody(db, world):
    ta = _holder(db, world)
    module = _birthday_module(db)
    module.enabled = False
    db.commit()
    assert rows(db) == []
    assert "birthday" not in db.get(UserAccessSnapshot, ta.id).snapshot["apps"]  # realigned silently
    module.enabled = True
    db.commit()
    assert rows(db) == []
    assert "birthday" in db.get(UserAccessSnapshot, ta.id).snapshot["apps"]


def test_a_personal_change_after_a_silent_global_change_reports_only_itself(db, world):
    ta = _holder(db, world)
    _birthday_module(db).enabled = False
    db.commit()
    _set_talent_role(db, ta, "TA_MANAGER")
    db.commit()
    [row] = live(db, ta.id)
    assert row.template_data["revoked"] == []  # the disabled application is not reported


def test_editing_a_role_definition_emails_nobody(db, world):
    from app.models.role import Permission, Role, RolePermission

    role = db.execute(select(Role).where(Role.key == "TA_MEMBER")).scalar_one()
    perm = Permission(key="talent.global_added", name="Global added", module_key=TALENT)
    db.add(perm)
    db.flush()
    db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.commit()
    assert rows(db) == []


def test_global_change_while_an_email_waits_never_leaks_into_the_folded_email(db, world):
    ta = _holder(db, world)
    _set_talent_role(db, ta, "TA_MANAGER")
    db.commit()  # unsent personal email
    [waiting] = live(db, ta.id)
    _birthday_module(db).enabled = False  # silent global change while it waits
    db.commit()
    [kept] = live(db, ta.id)
    assert kept.id == waiting.id  # the waiting email is kept intact
    _set_talent_role(db, ta, "TA_MEMBER")
    db.commit()
    _set_talent_role(db, ta, "TA_MANAGER")
    db.commit()  # follow-up personal change folds into it
    for row in live(db, ta.id):
        assert "DIJI Birthday" not in row.template_data["revoked"]


def test_user_specific_change_in_the_same_commit_as_a_global_one_is_still_emailed(db, world):
    ta = _holder(db, world)
    _birthday_module(db).enabled = False
    _set_talent_role(db, ta, "TA_MANAGER")
    db.commit()
    assert {r.recipient_user_id for r in live(db)} == {ta.id}


# --- admin retry never re-sends obsolete information ------------------------------------------


def test_retry_refuses_an_email_that_no_longer_matches_current_access(db, world, monkeypatch):
    from app.services.admin_service import ConflictError
    from app.services.email_admin_service import EmailAdminService

    _graph(monkeypatch, "internal_allowlist")
    set_transport_override(RecordingTransport())
    ta = _grant(db, world)
    assert dispatch_due() == {OutboxStatus.BLOCKED: 1}
    [blocked] = rows(db, ta.id)
    db.execute(delete(UserModuleRole).where(UserModuleRole.user_id == ta.id, UserModuleRole.module_key == "birthday"))
    db.commit()  # raw delete: access changed, the "granted" email is now false
    access_notifications.rebaseline_snapshots(db)
    with pytest.raises(ConflictError):
        EmailAdminService(db).retry(actor=world["super_admin"], outbox_id=blocked.id)


def test_retry_refuses_an_email_superseded_by_a_newer_one(db, world, monkeypatch):
    from app.services.admin_service import ConflictError
    from app.services.email_admin_service import EmailAdminService

    _graph(monkeypatch, "internal_allowlist")
    set_transport_override(RecordingTransport())
    ta = _grant(db, world)
    dispatch_due()
    [first] = rows(db, ta.id)
    _set_talent_role(db, ta, "TA_MANAGER")
    db.commit()
    with pytest.raises(ConflictError):
        EmailAdminService(db).retry(actor=world["super_admin"], outbox_id=first.id)


# --- DEV/UAT allowlist: explicit individual addresses only ------------------------------------


def test_whole_domain_test_recipients_are_refused_and_legacy_rows_ignored(db, world, api_client, monkeypatch):
    headers = auth_headers(api_client, "test-super-admin")
    assert api_client.post(f"{ADMIN}/test-recipients", json={"address": "@example.com"},
                           headers=headers).status_code == 422
    db.add(EmailTestRecipient(address="@example.com"))  # e.g. written before this rule
    db.commit()
    _graph(monkeypatch, "internal_allowlist")
    transport = RecordingTransport()
    set_transport_override(transport)
    _grant(db, world)
    assert dispatch_due() == {OutboxStatus.BLOCKED: 1}
    assert transport.sent == []


# --- dedicated notification permissions --------------------------------------------------------


def test_platform_admin_holds_the_dedicated_notification_permissions(db, world, api_client):
    headers = auth_headers(api_client, "test-platform-admin")
    assert api_client.get(f"{ADMIN}/outbox", headers=headers).status_code == 200
    assert api_client.put(f"{ADMIN}/events/{EVENT_GRANTED}", json={"enabled": True},
                          headers=headers).status_code == 200


def test_notification_endpoints_require_the_dedicated_permissions(db, world, api_client, monkeypatch):
    from app.api.routes import platform_admin

    assert platform_admin._VIEW_NOTIFICATIONS == "platform.admin.view_notifications"
    assert platform_admin._MANAGE_NOTIFICATIONS == "platform.admin.manage_notifications"
    from app.core.permissions import PLATFORM_ROLES

    roles = {r.key: set(r.permissions) for r in PLATFORM_ROLES}
    for key in ("SUPER_ADMIN", "PLATFORM_ADMIN"):
        assert {"platform.admin.view_notifications", "platform.admin.manage_notifications"} <= roles[key]
    assert roles["PLATFORM_USER"] == set()
    assert "platform.admin.manage_admins" not in roles["PLATFORM_ADMIN"]  # invariant kept


# --- history recipient search (Admin > Notifications filter) -----------------------------------


def _history_only(db, address):
    import uuid
    db.add(EmailOutbox(correlation_id=str(uuid.uuid4()), application_key="dijione", event_type=EVENT_GRANTED,
                       recipient_email=address, subject="[DijiOne] | Access Granted", template_key="access_change",
                       template_data={}, dedupe_key=f"test:{uuid.uuid4()}", status=OutboxStatus.SUBMITTED))
    db.commit()


def test_recipient_search_by_name_email_and_employee_number(db, world, api_client):
    headers = auth_headers(api_client, "test-super-admin")
    db.add(User(email="madushanka.w@dijital.example", full_name="Madushanka Weeriyasinghe",
                employee_number="10042", entra_object_id="oid-mad"))
    db.add(User(email="old.staff@dijital.example", full_name="Old Staff", is_active=False))
    db.commit()

    by_name = api_client.get(f"{ADMIN}/recipients", params={"q": "mad"}, headers=headers).json()
    assert [r["email"] for r in by_name] == ["madushanka.w@dijital.example"]
    assert by_name[0]["source"] == "user" and by_name[0]["has_photo"] is True
    assert api_client.get(f"{ADMIN}/recipients", params={"q": "OLD.STAFF@"}, headers=headers).json()[0][
        "is_active"] is False
    assert [r["full_name"] for r in api_client.get(f"{ADMIN}/recipients", params={"q": "1004"},
                                                    headers=headers).json()] == ["Madushanka Weeriyasinghe"]
    assert api_client.get(f"{ADMIN}/recipients", params={"q": "zzz-nobody"}, headers=headers).json() == []
    assert api_client.get(f"{ADMIN}/recipients", params={"q": "m"}, headers=headers).status_code == 422


def test_recipient_search_includes_history_only_addresses_and_is_read_only(db, world, api_client):
    from app.models.email_notification import EmailTestRecipient
    headers = auth_headers(api_client, "test-super-admin")
    _history_only(db, "svc-payroll@dijital.example")
    before_outbox, before_rcpt = len(rows(db)), db.execute(select(EmailTestRecipient)).all()
    found = api_client.get(f"{ADMIN}/recipients", params={"q": "svc-pay"}, headers=headers).json()
    assert found == [{"source": "history", "user_id": None, "full_name": None, "email": "svc-payroll@dijital.example",
                      "employee_number": None, "is_active": None, "has_photo": False}]
    assert len(rows(db)) == before_outbox
    assert db.execute(select(EmailTestRecipient)).all() == before_rcpt


def test_recipient_filter_treats_wildcards_literally(db, world, api_client):
    headers = auth_headers(api_client, "test-super-admin")
    _history_only(db, "a_b@dijital.example")
    _history_only(db, "axb@dijital.example")
    listing = api_client.get(f"{ADMIN}/outbox", params={"recipient": "a_b@"}, headers=headers).json()
    assert [i["recipient_email"] for i in listing["items"]] == ["a_b@dijital.example"]
    assert api_client.get(f"{ADMIN}/outbox", params={"recipient": "%"}, headers=headers).json()["total"] == 0
    assert api_client.get(f"{ADMIN}/recipients", params={"q": "a_b"}, headers=headers).json()[0]["email"] == \
        "a_b@dijital.example"


@pytest.mark.parametrize("persona", ["test-ta", "test-abc-client"])
def test_ordinary_users_cannot_search_recipients(db, world, api_client, persona):
    assert api_client.get(f"{ADMIN}/recipients", params={"q": "ta"},
                          headers=auth_headers(api_client, persona)).status_code == 403


def test_platform_admin_can_search_recipients_but_view_as_cannot(db, world, api_client, monkeypatch):
    assert api_client.get(f"{ADMIN}/recipients", params={"q": "ta"},
                          headers=auth_headers(api_client, "test-platform-admin")).status_code == 200
    monkeypatch.setenv("VIEW_AS_ENABLED", "true")
    get_settings.cache_clear()
    ta = make_eligible(db.get(User, world["ta_user"].id))
    db.commit()
    started = api_client.post("/api/platform/admin/view-as", json={"target_user_id": ta.id},
                              headers=auth_headers(api_client, "test-super-admin"))
    view_as = {"Authorization": f"Bearer {started.json()['access_token']}"}
    assert api_client.get(f"{ADMIN}/recipients", params={"q": "ta"}, headers=view_as).status_code == 403
