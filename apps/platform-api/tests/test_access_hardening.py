"""Central Admin hardening: no self-grant (Super Admin break-glass only, audited and notified), no
change to an administrator's access or status without the right to manage administrators, and no
group change that reaches the actor or an administrator."""

from sqlalchemy import select

from app.models.access_group import AccessGroup, UserGroupMembership
from app.models.audit_log import AuditLog
from app.models.notification import Notification
from app.models.user import User, UserModuleRole
from tests.conftest import auth_headers

ADMIN = "/api/platform/admin"
TALENT = "talent-flow"
SCOPE = {"all_clients": True, "client_ids": []}


def _assign(api_client, who, user_id, **extra):
    return api_client.put(f"{ADMIN}/users/{user_id}/modules/{TALENT}", headers=auth_headers(api_client, who),
                          json={"role": "TA_MANAGER", "client_scope": SCOPE, **extra})


def test_platform_admin_cannot_grant_itself_an_application_role(api_client, db, two_tenant_world):
    admin = two_tenant_world["platform_admin"]
    resp = _assign(api_client, "test-platform-admin", admin.id)
    assert resp.status_code == 403 and "own access" in resp.json()["detail"]
    assert db.execute(select(UserModuleRole).where(UserModuleRole.user_id == admin.id)).first() is None


def test_super_admin_self_grant_needs_a_break_glass_reason_and_tells_other_super_admins(api_client, db, two_tenant_world):
    me = two_tenant_world["super_admin"]
    other = User(email="other-super@example.com", full_name="Other Super", platform_role="SUPER_ADMIN")
    db.add(other)
    db.commit()
    assert _assign(api_client, "test-super-admin", me.id).status_code == 403
    assert _assign(api_client, "test-super-admin", me.id, break_glass_reason="short").status_code == 403
    resp = _assign(api_client, "test-super-admin", me.id, break_glass_reason="Covering the TA desk during an outage")
    assert resp.status_code == 200
    entry = db.execute(select(AuditLog).where(AuditLog.action == "module_assignment.created")).scalars().one()
    assert '"break_glass": true' in entry.event_metadata and "TA desk" in entry.event_metadata
    notes = db.execute(select(Notification).where(Notification.type == "ACCESS_BREAK_GLASS")).scalars().all()
    assert [n.user_id for n in notes] == [other.id]


def test_only_a_super_admin_changes_an_administrators_access_or_status(api_client, db, two_tenant_world):
    super_admin, platform_admin = two_tenant_world["super_admin"], two_tenant_world["platform_admin"]
    assert _assign(api_client, "test-platform-admin", super_admin.id).status_code == 403
    deactivate = api_client.patch(f"{ADMIN}/users/{super_admin.id}/status", json={"is_active": False},
                                  headers=auth_headers(api_client, "test-platform-admin"))
    assert deactivate.status_code == 403
    db.expire_all()
    assert db.get(User, super_admin.id).is_active
    # A Super Admin may.
    assert _assign(api_client, "test-super-admin", platform_admin.id).status_code == 200
    assert api_client.patch(f"{ADMIN}/users/{platform_admin.id}/status", json={"is_active": False},
                            headers=auth_headers(api_client, "test-super-admin")).status_code == 200
    # Ordinary users are unaffected.
    assert _assign(api_client, "test-super-admin", two_tenant_world["ta_user"].id).status_code == 200


def _group_with(db, *members):
    group = AccessGroup(key="team", display_name="Team")
    db.add(group)
    db.flush()
    for m in members:
        db.add(UserGroupMembership(user_id=m.id, access_group_id=group.id))
    db.commit()
    return group


def test_no_self_grant_through_groups(api_client, db, two_tenant_world):
    admin = two_tenant_world["platform_admin"]
    group = _group_with(db, two_tenant_world["ta_user"])
    headers = auth_headers(api_client, "test-platform-admin")
    assert api_client.post(f"{ADMIN}/groups/{group.id}/members", json={"user_id": admin.id}, headers=headers).status_code == 403
    db.add(UserGroupMembership(user_id=admin.id, access_group_id=group.id))
    db.commit()
    resp = api_client.put(f"{ADMIN}/groups/{group.id}/modules/{TALENT}", headers=headers,
                          json={"role": "TA_MANAGER", "client_scope": SCOPE})
    assert resp.status_code == 403  # the actor is a member: it would change their own access


def test_groups_with_administrators_need_a_super_admin(api_client, db, two_tenant_world):
    group = _group_with(db, two_tenant_world["super_admin"], two_tenant_world["ta_user"])
    body = {"role": "TA_MEMBER", "client_scope": SCOPE}
    assert api_client.put(f"{ADMIN}/groups/{group.id}/modules/{TALENT}", json=body,
                          headers=auth_headers(api_client, "test-platform-admin")).status_code == 403
    plain = AccessGroup(key="plain", display_name="Plain")
    db.add(plain)
    db.flush()
    db.add(UserGroupMembership(user_id=two_tenant_world["cs_user"].id, access_group_id=plain.id))
    db.commit()
    assert api_client.put(f"{ADMIN}/groups/{plain.id}/modules/{TALENT}", json=body,
                          headers=auth_headers(api_client, "test-platform-admin")).status_code == 200


def test_central_changes_are_audited_with_the_central_channel(api_client, db, two_tenant_world):
    assert _assign(api_client, "test-platform-admin", two_tenant_world["cs_user"].id).status_code == 200
    entry = db.execute(select(AuditLog).where(AuditLog.action == "module_assignment.updated")).scalars().one()
    assert '"channel": "CENTRAL"' in entry.event_metadata
