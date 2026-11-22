"""Access notifications v2: application-aware events across platform and application access.

Covers the delegated Access-page path for every application with delegation (driven by the
registry, never by module names), single-application subjects from the registry, role, client
scope, delegated administration and Admin Center changes, one consolidated email for several
applications, origin metadata, rendering, and the silent v1 -> v2 snapshot upgrade.
"""

import copy

import pytest
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.permissions import DELEGATION
from app.db.base import utcnow
from app.models.access_group import AccessGroup, GroupModuleRole, UserGroupMembership
from app.models.email_notification import EmailOutbox, OutboxStatus, UserAccessSnapshot
from app.models.module import ApplicationModule
from app.models.user import User, UserModuleRole
from app.services import access_notifications as an
from app.services.email_dispatcher import dispatch_due, set_transport_override
from tests.conftest import auth_headers, make_eligible

TALENT = "talent-flow"
ADMIN = "/api/platform/admin"
ABC, XYZ = 1, 2  # platform Client.id, seeded in this order by conftest


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setenv("DELEGATED_ACCESS_ENABLED", "true")
    monkeypatch.setenv("ENTRA_INTERNAL_EMAIL_DOMAINS", "example.com")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    set_transport_override(None)


def rows(db, user_id=None):
    db.expire_all()
    stmt = select(EmailOutbox).order_by(EmailOutbox.id)
    if user_id is not None:
        stmt = stmt.where(EmailOutbox.recipient_user_id == user_id)
    return [r for r in db.execute(stmt).scalars() if r.status != OutboxStatus.SUPERSEDED]


def snapshot(db, user_id):
    db.expire_all()
    return db.get(UserAccessSnapshot, user_id).snapshot


@pytest.fixture()
def world(db, two_tenant_world):
    """Registry rows for every application with delegation (names from its definition)."""
    existing = set(db.execute(select(ApplicationModule.key)).scalars())
    for key, definition in DELEGATION.items():
        if key not in existing:
            db.add(ApplicationModule(key=key, name=definition.display_name, description="", route=f"/{key}",
                                     supports_client_scope=key == TALENT))
    people = {}
    for key in ("tom", "pat", "sam"):
        user = User(email=f"{key}@example.com", full_name=key.title(), persona_key=f"test-{key}")
        make_eligible(user)
        db.add(user)
        people[key] = user
    db.commit()
    for name in ("super_admin", "platform_admin"):
        make_eligible(db.get(User, two_tenant_world[name].id))
    db.commit()
    db.execute(delete(EmailOutbox))
    db.commit()
    return {**two_tenant_world, **people}


def h(api_client, persona="test-super-admin"):
    return auth_headers(api_client, persona)


def name_of(db, key):
    return an._module_names(db)[key]


def _scope(clients):
    return {"all_clients": clients == "ALL", "client_ids": [] if clients == "ALL" else clients}


def central(api_client, user_id, module, role, clients="ALL"):
    resp = api_client.put(f"{ADMIN}/users/{user_id}/modules/{module}",
                          json={"role": role, "client_scope": _scope(clients)}, headers=h(api_client))
    assert resp.status_code == 200, resp.text


def make_administrator(db, api_client, user, module):
    """An access administrator of ``module`` for ``user``: a saved appointment, or, where the
    application only uses implied administrators, the role that implies one."""
    definition = DELEGATION[module]
    body = {"grantable_roles": list(definition.delegable_roles), "can_appoint_admins": False}
    if module == TALENT:
        body["client_authority"] = _scope("ALL")
    resp = api_client.put(f"{ADMIN}/applications/{module}/administrators/{user.id}", json=body, headers=h(api_client))
    if resp.status_code == 403 and definition.implied_by:
        implying_role = definition.implied_by[0][0]
        central(api_client, user.id, module, implying_role)
        return
    assert resp.status_code == 200, resp.text


def _other_module(key):
    return next(k for k in sorted(DELEGATION) if k != key)


# --- the delegated Access-page path, every application with delegation ------------------------


@pytest.mark.parametrize("module", sorted(DELEGATION))
def test_application_access_page_sends_application_specific_emails(db, world, api_client, module):
    """Contract for every platform-managed application: grant, role change and revoke made on
    the application's own Access page send one email each, named after the application."""
    definition = DELEGATION[module]
    tom, pat = world["tom"], world["pat"]
    make_administrator(db, api_client, tom, module)
    other = _other_module(module)
    central(api_client, pat.id, other, DELEGATION[other].delegable_roles[0])  # pat already has access elsewhere
    dispatch_due()
    had = module in snapshot(db, pat.id)["apps"]  # e.g. default employee access

    role = next(r for r in definition.delegable_roles if r not in {i for i, _ in definition.implied_by})
    body = {"role": role} | ({"client_scope": _scope("ALL")} if module == TALENT else {})
    resp = api_client.put(f"/api/access/{module}/users/{pat.id}", json=body, headers=h(api_client, "test-tom"))
    assert resp.status_code == 200, resp.text
    granted = rows(db, pat.id)[-1]
    expected = an.EVENT_ROLE_UPDATED if had else an.EVENT_GRANTED
    assert granted.event_type == expected and granted.application_key == module
    assert granted.subject == f"[{name_of(db, module)}] | {an.EVENTS[expected][0]}"
    origin = granted.template_data["origin"]
    assert origin["channel"] == "APPLICATION" and origin["source_application_key"] == module
    assert origin["actor_user_id"] == tom.id and origin["audit_ids"]
    assert granted.template_data["route"] == f"/{module}"
    dispatch_due()

    implying = {r for r, _ in definition.implied_by}  # those make the person an administrator
    manageable = [r for r in definition.delegable_roles if r not in implying]
    if len(manageable) > 1:
        body["role"] = manageable[1]
        assert api_client.put(f"/api/access/{module}/users/{pat.id}", json=body,
                              headers=h(api_client, "test-tom")).status_code == 200
        changed = rows(db, pat.id)[-1]
        assert changed.application_key == module and changed.event_type in (an.EVENT_ROLE_UPDATED, an.EVENT_UPDATED)
        dispatch_due()

    count = len(rows(db, pat.id))
    resp = api_client.post(f"/api/access/{module}/users/{pat.id}/revoke", json={"reason": "test"},
                           headers=h(api_client, "test-tom"))
    assert resp.status_code == 200, resp.text
    after = rows(db, pat.id)
    if had:  # default access remains: back to the default role, not a revocation
        assert len(after) == count + 1 and after[-1].application_key == module
    else:
        assert len(after) == count + 1 and after[-1].event_type == an.EVENT_REVOKED
        assert after[-1].subject == f"[{name_of(db, module)}] | Access Revoked"


# --- roles, client scope, administration, Admin Center ---------------------------------------


def test_role_swap_with_identical_permissions_is_a_role_update(db, world, api_client):
    sam = world["sam"]
    central(api_client, sam.id, TALENT, "CUSTOMER_SUCCESS")
    dispatch_due()
    central(api_client, sam.id, TALENT, "TA_MANAGER")
    row = rows(db, sam.id)[-1]
    assert (row.event_type, row.subject) == (an.EVENT_ROLE_UPDATED, f"[{name_of(db, TALENT)}] | Role Updated")


def test_client_scope_change_is_detected_by_identity_not_count(db, world, api_client):
    sam = world["sam"]
    central(api_client, sam.id, TALENT, "TA_MEMBER", [ABC])
    dispatch_due()
    before = len(rows(db, sam.id))
    central(api_client, sam.id, TALENT, "TA_MEMBER", [XYZ])  # one client -> a different one client
    [row] = rows(db, sam.id)[before:]
    assert (row.event_type, row.subject) == (an.EVENT_SCOPE_UPDATED, f"[{name_of(db, TALENT)}] | Client Access Updated")
    dispatch_due()
    central(api_client, sam.id, TALENT, "TA_MEMBER", [XYZ])  # same again: no-op
    assert len(rows(db, sam.id)) == before + 1
    body = an.render_access_email(row, portal_url="https://dijione.example/")
    assert "XYZ" not in str(body) and "client" not in " ".join(body.paragraphs).lower().replace("client access", "")


def test_delegated_administration_change_is_its_own_event(db, world, api_client):
    tom = world["tom"]
    central(api_client, tom.id, TALENT, "TA_MEMBER")
    dispatch_due()
    resp = api_client.put(f"{ADMIN}/applications/{TALENT}/administrators/{tom.id}",
                          json={"grantable_roles": ["TA_MEMBER"], "can_appoint_admins": False,
                                "client_authority": _scope("ALL")}, headers=h(api_client))
    assert resp.status_code == 200, resp.text
    row = rows(db, tom.id)[-1]
    assert (row.event_type, row.application_key) == (an.EVENT_ADMINISTRATION_UPDATED, TALENT)
    assert row.template_data["administration"] == [name_of(db, TALENT)] and row.template_data["granted"] == []
    dispatch_due()
    resp = api_client.put(f"{ADMIN}/applications/{TALENT}/administrators/{tom.id}",
                          json={"grantable_roles": ["TA_MEMBER", "CUSTOMER_SUCCESS"], "can_appoint_admins": False,
                                "client_authority": _scope("ALL")},
                          headers=h(api_client))
    assert resp.status_code == 200
    assert rows(db, tom.id)[-1].event_type == an.EVENT_ADMINISTRATION_UPDATED


def test_admin_center_access_changes(db, world, api_client):
    sam = world["sam"]
    central(api_client, sam.id, TALENT, "TA_MEMBER")
    dispatch_due()

    def set_role(role):
        resp = api_client.patch(f"{ADMIN}/users/{sam.id}/platform-role", json={"platform_role": role}, headers=h(api_client))
        assert resp.status_code == 200, resp.text
        dispatch_due()
        return rows(db, sam.id)[-1]

    granted = set_role("PLATFORM_ADMIN")
    assert (granted.subject, granted.application_key) == (
        f"[{an.ADMIN_CENTER_NAME}] | Access Granted", an.ADMIN_CENTER_KEY)
    assert set_role("SUPER_ADMIN").subject == f"[{an.ADMIN_CENTER_NAME}] | Role Updated"
    assert set_role("PLATFORM_USER").subject == f"[{an.ADMIN_CENTER_NAME}] | Access Revoked"
    count = len(rows(db, sam.id))
    sam_row = db.get(User, sam.id)
    sam_row.platform_role = "PLATFORM_USER"  # no-op
    db.commit()
    assert len(rows(db, sam.id)) == count


# --- several applications, groups, folding ------------------------------------------------------


def test_one_action_on_several_applications_sends_one_dijione_email(db, world):
    sam = world["sam"]
    db.add(UserModuleRole(user_id=sam.id, module_key=TALENT, role="TA_MEMBER"))
    db.commit()
    dispatch_due()
    others = [k for k in sorted(DELEGATION) if k != TALENT][:2]
    for key in others:
        db.add(UserModuleRole(user_id=sam.id, module_key=key, role=DELEGATION[key].delegable_roles[0]))
    db.commit()
    [row] = rows(db, sam.id)[1:]
    assert (row.application_key, row.subject) == ("dijione", "[DijiOne] | Access Granted")
    assert "route" not in row.template_data


def test_follow_up_change_folds_and_is_reclassified(db, world):
    sam = world["sam"]
    db.add(UserModuleRole(user_id=sam.id, module_key=TALENT, role="TA_MEMBER"))
    db.commit()
    dispatch_due()
    a, b = [k for k in sorted(DELEGATION) if k != TALENT][:2]
    db.add(UserModuleRole(user_id=sam.id, module_key=a, role=DELEGATION[a].delegable_roles[0]))
    db.commit()
    assert rows(db, sam.id)[-1].application_key == a
    db.add(UserModuleRole(user_id=sam.id, module_key=b, role=DELEGATION[b].delegable_roles[0]))
    db.commit()
    live = rows(db, sam.id)
    assert live[-1].application_key == "dijione" and len(live) == 2  # the single-app email was superseded


def test_group_derived_access_names_the_group_and_source_changes_are_silent(db, world):
    sam = world["sam"]
    db.add(UserModuleRole(user_id=sam.id, module_key=TALENT, role="TA_MEMBER"))
    db.commit()
    dispatch_due()
    key = _other_module(TALENT)
    role = DELEGATION[key].delegable_roles[0]
    group = AccessGroup(key="v2-group", display_name="Site Leads")
    db.add(group)
    db.flush()
    db.add(GroupModuleRole(access_group_id=group.id, module_key=key, role=role))
    db.commit()
    assert len(rows(db, sam.id)) == 1  # nobody in the group yet
    db.add(UserGroupMembership(user_id=sam.id, access_group_id=group.id))
    db.commit()
    row = rows(db, sam.id)[-1]
    assert (row.event_type, row.application_key) == (an.EVENT_GRANTED, key)
    dispatch_due()
    count = len(rows(db, sam.id))
    db.add(UserModuleRole(user_id=sam.id, module_key=key, role=role))  # duplicates the group grant
    db.commit()
    membership = db.execute(select(UserGroupMembership).where(UserGroupMembership.user_id == sam.id)).scalar_one()
    db.delete(membership)  # now direct instead of through the group: same access
    db.commit()
    assert len(rows(db, sam.id)) == count


# --- safety --------------------------------------------------------------------------------------


def test_rollback_and_registry_changes_send_nothing(db, world):
    sam = world["sam"]
    db.add(UserModuleRole(user_id=sam.id, module_key=TALENT, role="TA_MEMBER"))
    db.commit()
    dispatch_due()
    count = len(rows(db))
    db.add(UserModuleRole(user_id=sam.id, module_key=_other_module(TALENT), role="X"))
    db.rollback()
    module = db.execute(select(ApplicationModule).where(ApplicationModule.key == TALENT)).scalar_one()
    module.name = "Renamed TalentFlow"
    db.commit()
    module.enabled = False
    db.commit()
    module.enabled = True
    db.commit()
    assert len(rows(db)) == count


def test_notification_failure_never_breaks_the_access_change(db, world, monkeypatch):
    sam = world["sam"]
    monkeypatch.setattr(an, "_origin", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    db.add(UserModuleRole(user_id=sam.id, module_key=TALENT, role="TA_MEMBER"))
    db.commit()
    db.expire_all()
    assert db.execute(select(UserModuleRole).where(UserModuleRole.user_id == sam.id)).scalar_one()


def _as_v1(snap: dict) -> dict:
    """A snapshot as v1 stored it: active plus permissions/default_only per application."""
    return {"active": snap["active"], "apps": {k: {"permissions": v["permissions"], "default_only": v["default_only"]}
                                               for k, v in snap["apps"].items()}}


def _store_v1(db, user_id):
    snap = db.get(UserAccessSnapshot, user_id)
    snap.snapshot = _as_v1(copy.deepcopy(snap.snapshot))
    db.commit()


def test_v1_snapshots_upgrade_silently_and_v2_changes_are_detected_after(db, world, api_client):
    sam = world["sam"]
    central(api_client, sam.id, TALENT, "CUSTOMER_SUCCESS")
    dispatch_due()
    _store_v1(db, sam.id)
    count = len(rows(db, sam.id))
    central(api_client, sam.id, TALENT, "TA_MANAGER")  # identical permissions: v1 could not see it
    assert len(rows(db, sam.id)) == count
    assert snapshot(db, sam.id)["v"] == 2
    central(api_client, sam.id, TALENT, "CUSTOMER_SUCCESS")  # now v2: detected
    assert rows(db, sam.id)[-1].event_type == an.EVENT_ROLE_UPDATED


def test_v1_permission_change_still_emails_during_the_upgrade(db, world, api_client):
    sam = world["sam"]
    central(api_client, sam.id, TALENT, "TA_MEMBER")
    dispatch_due()
    _store_v1(db, sam.id)
    central(api_client, sam.id, TALENT, "TA_MANAGER")
    assert rows(db, sam.id)[-1].event_type == an.EVENT_UPDATED


def test_startup_rebaseline_is_silent_keeps_pending_and_respects_concurrent_updates(db, world):
    sam, pat = world["sam"], world["pat"]
    for user in (sam, pat):
        db.add(UserModuleRole(user_id=user.id, module_key=TALENT, role="TA_MEMBER"))
    db.commit()
    dispatch_due()
    key = _other_module(TALENT)
    db.add(UserModuleRole(user_id=sam.id, module_key=key, role=DELEGATION[key].delegable_roles[0]))
    db.commit()  # sam: a legitimate email still pending
    pending = rows(db, sam.id)[-1]
    assert pending.status == OutboxStatus.PENDING
    for user in (sam, pat):
        _store_v1(db, user.id)
    before = len(rows(db))

    stale = db.get(UserAccessSnapshot, pat.id).updated_at
    snap = db.get(UserAccessSnapshot, pat.id)
    snap.updated_at = utcnow()  # a concurrent change wrote pat's row after it was read
    db.commit()
    assert an.realign_silently(db, pat.id, expected_stamp=stale) is False
    db.commit()
    assert "v" not in snapshot(db, pat.id)  # not overwritten

    changed = an.rebaseline_snapshots(db)
    assert changed >= 2 and len(rows(db)) == before  # everyone realigned, nobody emailed
    db.expire_all()
    assert db.get(EmailOutbox, pending.id).status == OutboxStatus.PENDING
    assert snapshot(db, sam.id)["v"] == 2 and snapshot(db, pat.id)["v"] == 2


def test_v2_snapshots_stay_readable_by_v1_logic(db, world):
    """Rollback safety: v1 compared only active/permissions/default_only; v2 keeps them as they were."""
    sam = world["sam"]
    db.add(UserModuleRole(user_id=sam.id, module_key=TALENT, role="TA_MEMBER"))
    db.commit()
    v2 = snapshot(db, sam.id)
    assert _as_v1(v2)["apps"][TALENT]["permissions"] == v2["apps"][TALENT]["permissions"]
    assert set(v2["apps"][TALENT]) >= {"permissions", "default_only"} and v2["active"] is True


# --- rendering and administration ----------------------------------------------------------------


def test_single_application_email_names_the_application_and_links_to_it(db, world):
    sam = world["sam"]
    db.add(UserModuleRole(user_id=sam.id, module_key=TALENT, role="TA_MEMBER"))
    db.commit()
    dispatch_due()
    key = _other_module(TALENT)
    db.add(UserModuleRole(user_id=sam.id, module_key=key, role=DELEGATION[key].delegable_roles[0]))
    db.commit()
    row = rows(db, sam.id)[-1]
    content = an.render_access_email(row, portal_url="https://dijione.example/")
    assert content.application_name == name_of(db, key)
    assert name_of(db, key) in content.heading
    assert content.action_url == f"https://dijione.example/{key}"
    row.template_data = dict(row.template_data, route="https://evil.example/")  # never trusted
    assert an.render_access_email(row, portal_url="https://dijione.example/").action_url == "https://dijione.example/"


def test_admin_details_show_origin_and_registry_names(db, world, api_client):
    tom, pat = world["tom"], world["pat"]
    key = _other_module(TALENT)
    definition = DELEGATION[key]
    make_administrator(db, api_client, tom, key)
    central(api_client, pat.id, TALENT, "TA_MEMBER")
    dispatch_due()
    api_client.put(f"/api/access/{key}/users/{pat.id}", json={"role": definition.delegable_roles[0]},
                   headers=h(api_client, "test-tom"))
    row = rows(db, pat.id)[-1]
    detail = api_client.get(f"{ADMIN}/notifications/outbox/{row.id}", headers=h(api_client)).json()
    assert detail["application_name"] == name_of(db, key)
    assert detail["origin"]["channel"] == "APPLICATION"
    assert detail["origin"]["source_application_name"] == name_of(db, key)
    assert detail["origin"]["actor_name"] == "Tom"
    summary = api_client.get(f"{ADMIN}/notifications/summary", headers=h(api_client)).json()
    assert {"key": key, "name": name_of(db, key)} in summary["applications"]
    events = {e["event_type"] for e in api_client.get(f"{ADMIN}/notifications/events", headers=h(api_client)).json()}
    assert {an.EVENT_ROLE_UPDATED, an.EVENT_SCOPE_UPDATED, an.EVENT_ADMINISTRATION_UPDATED} <= events


def test_new_events_can_be_switched_off(db, world, api_client):
    sam = world["sam"]
    resp = api_client.put(f"{ADMIN}/notifications/events/{an.EVENT_ROLE_UPDATED}", json={"enabled": False},
                          headers=h(api_client))
    assert resp.status_code == 200
    central(api_client, sam.id, TALENT, "CUSTOMER_SUCCESS")
    dispatch_due()
    count = len(rows(db, sam.id))
    central(api_client, sam.id, TALENT, "TA_MANAGER")
    assert len(rows(db, sam.id)) == count


# --- v1 -> v2 transition: nothing legitimate is lost --------------------------------------------


def test_role_change_folded_into_an_unsent_v1_email_is_not_lost(db, world, api_client):
    """An email still unsent from before v2 starts from a v1 snapshot; a role change folded into
    it must still be reported (the documented transition gap, now closed)."""
    sam = world["sam"]
    central(api_client, sam.id, TALENT, "CUSTOMER_SUCCESS")
    dispatch_due()
    key = _other_module(TALENT)
    db.add(UserModuleRole(user_id=sam.id, module_key=key, role=DELEGATION[key].delegable_roles[0]))
    db.commit()
    unsent = rows(db, sam.id)[-1]
    assert unsent.status == OutboxStatus.PENDING
    unsent.from_snapshot = _as_v1(copy.deepcopy(unsent.from_snapshot))  # queued by the v1 revision
    db.commit()
    central(api_client, sam.id, TALENT, "TA_MANAGER")  # identical permissions: role only
    row = rows(db, sam.id)[-1]
    kinds = {c["name"]: c["kind"] for c in row.template_data["changes"]}
    assert kinds == {name_of(db, key): "granted", name_of(db, TALENT): "role"}
    assert row.subject == "[DijiOne] | Access Updated"


def test_admin_center_change_folded_into_an_unsent_v1_email_is_not_lost(db, world, api_client):
    sam = world["sam"]
    central(api_client, sam.id, TALENT, "TA_MEMBER")
    dispatch_due()
    key = _other_module(TALENT)
    db.add(UserModuleRole(user_id=sam.id, module_key=key, role=DELEGATION[key].delegable_roles[0]))
    db.commit()
    unsent = rows(db, sam.id)[-1]
    unsent.from_snapshot = _as_v1(copy.deepcopy(unsent.from_snapshot))
    db.commit()
    resp = api_client.patch(f"{ADMIN}/users/{sam.id}/platform-role", json={"platform_role": "PLATFORM_ADMIN"},
                            headers=h(api_client))
    assert resp.status_code == 200
    kinds = {c["name"]: c["kind"] for c in rows(db, sam.id)[-1].template_data["changes"]}
    assert kinds[an.ADMIN_CENTER_NAME] == "granted"


def test_v1_snapshot_upgrade_is_silent_targets_only_v1_and_respects_concurrent_writes(db, world):
    sam, pat = world["sam"], world["pat"]
    for user in (sam, pat):
        db.add(UserModuleRole(user_id=user.id, module_key=TALENT, role="TA_MEMBER"))
    db.commit()
    dispatch_due()
    _store_v1(db, sam.id)
    pat_stamp = db.get(UserAccessSnapshot, pat.id).updated_at
    before = len(rows(db))
    assert an.upgrade_v1_snapshots(db) >= 1
    assert snapshot(db, sam.id)["v"] == 2 and len(rows(db)) == before
    assert db.get(UserAccessSnapshot, pat.id).updated_at == pat_stamp  # v2 rows untouched
    assert an.upgrade_v1_snapshots(db) == 0  # idempotent


def test_upgrade_completes_the_starting_point_of_an_unsent_v1_email(db, world):
    sam = world["sam"]
    db.add(UserModuleRole(user_id=sam.id, module_key=TALENT, role="TA_MEMBER"))
    db.commit()
    dispatch_due()
    key = _other_module(TALENT)
    db.add(UserModuleRole(user_id=sam.id, module_key=key, role=DELEGATION[key].delegable_roles[0]))
    db.commit()
    unsent = rows(db, sam.id)[-1]
    unsent.from_snapshot = _as_v1(copy.deepcopy(unsent.from_snapshot))
    _store_v1(db, sam.id)
    an.upgrade_v1_snapshots(db)
    db.expire_all()
    row = db.get(EmailOutbox, unsent.id)
    assert row.status == OutboxStatus.PENDING
    assert row.from_snapshot["v"] == 2 and "roles" in row.from_snapshot["apps"][TALENT]


def test_upgrade_from_snapshot_keeps_unknown_where_permissions_differ():
    v1 = {"active": True, "apps": {"a": {"permissions": ["x"], "default_only": False}}}
    ref = {"v": 2, "active": True, "platform_role": None,
           "apps": {"a": {"permissions": ["x", "y"], "roles": ["R"], "administers": [], "default_only": False}}}
    out = an.upgrade_from_snapshot(v1, ref)
    assert "roles" not in out["apps"]["a"] and out["platform_role"] is None
    assert an.upgrade_from_snapshot(ref, v1) is ref  # already v2: unchanged
