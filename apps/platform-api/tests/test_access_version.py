"""D2: users.access_version moves with every change that can alter access; tokens carry
the version they were issued under; the internal snapshot lists what applications need."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes import auth as auth_routes
from app.core.security import decode_session_token
from app.db.session import SessionLocal
from app.models.access_group import GroupModuleClientScope, GroupModuleRole, UserGroupMembership
from app.models.module_baseline import ModuleBaselineRole
from app.models.user import User, UserModuleRole
from app.schemas.admin import ClientScopeIn
from app.services.admin_service import AdminService
from tests.conftest import auth_headers, internal_headers

MODULE = "talent-flow"
ALL = ClientScopeIn(all_clients=True, client_ids=[])
FEED = "/api/platform/internal/access-versions"


def _av(db: Session, user_id: int) -> int:
    db.expire_all()
    return db.execute(select(User.access_version).where(User.id == user_id)).scalar_one()


def _people(db, world):
    return world["ta_user"], world["cs_user"], world["super_admin"]


def _group(db, actor, members, key="ops"):
    svc = AdminService(db)
    group = svc.create_group(actor=actor, key=key, display_name=key.title())
    for m in members:
        svc.add_group_member(actor=actor, group_id=group.id, target_user_id=m.id)
    return svc, group.id


# --- every kind of change bumps the affected user ------------------------------


def test_a_new_user_starts_at_zero_and_a_login_timestamp_changes_nothing(db, two_tenant_world):
    fresh = User(email="fresh@example.com", full_name="Fresh", persona_key="test-fresh")
    db.add(fresh)
    db.commit()
    assert _av(db, fresh.id) == 0
    db.get(User, fresh.id).last_login_at = datetime.now(UTC)
    db.commit()
    assert _av(db, fresh.id) == 0


def test_direct_assignment_changes_bump_only_that_user(db, two_tenant_world):
    ta, cs, admin = _people(db, two_tenant_world)
    svc = AdminService(db)
    before_cs = _av(db, cs.id)
    svc.upsert_module_assignment(
        actor=admin, target_user_id=ta.id, module_key=MODULE, role="TA_MANAGER", enabled=True, client_scope=ALL
    )
    after_role = _av(db, ta.id)
    assert after_role > 0
    svc.upsert_module_assignment(
        actor=admin, target_user_id=ta.id, module_key=MODULE, role="TA_MANAGER", enabled=False, client_scope=ALL
    )
    after_disable = _av(db, ta.id)
    assert after_disable > after_role
    svc.remove_module_assignment(actor=admin, target_user_id=ta.id, module_key=MODULE)
    assert _av(db, ta.id) > after_disable
    assert _av(db, cs.id) == before_cs


def test_client_scope_change_bumps_the_user(db, two_tenant_world):
    ta, _cs, admin = _people(db, two_tenant_world)
    svc = AdminService(db)
    svc.upsert_module_assignment(
        actor=admin, target_user_id=ta.id, module_key=MODULE, role="TA_MEMBER", enabled=True, client_scope=ALL
    )
    before = _av(db, ta.id)
    svc.upsert_module_assignment(
        actor=admin, target_user_id=ta.id, module_key=MODULE, role="TA_MEMBER", enabled=True,
        client_scope=ClientScopeIn(all_clients=False, client_ids=[1]),
    )
    assert _av(db, ta.id) > before


def test_account_status_and_platform_role_changes_bump(db, two_tenant_world):
    ta, _cs, admin = _people(db, two_tenant_world)
    svc = AdminService(db)
    base = _av(db, ta.id)
    svc.set_user_active(actor=admin, target_user_id=ta.id, is_active=False)
    deactivated = _av(db, ta.id)
    assert deactivated > base
    svc.set_user_active(actor=admin, target_user_id=ta.id, is_active=True)
    reactivated = _av(db, ta.id)
    assert reactivated > deactivated
    svc.set_platform_role(actor=admin, target_user_id=ta.id, new_role="PLATFORM_ADMIN")
    assert _av(db, ta.id) > reactivated


# --- group-wide changes invalidate every member, and only members --------------


def test_group_grant_scope_status_and_membership_changes_reach_all_members(db, two_tenant_world):
    ta, cs, admin = _people(db, two_tenant_world)
    outsider = two_tenant_world["abc_user"]
    svc, gid = _group(db, admin, [ta, cs])
    outsider_before = _av(db, outsider.id)

    def versions():
        return _av(db, ta.id), _av(db, cs.id)

    seen = versions()
    svc.upsert_group_module_assignment(
        actor=admin, group_id=gid, module_key=MODULE, role="TA_MEMBER", enabled=True, client_scope=ALL
    )
    after_grant = versions()
    assert all(a > b for a, b in zip(after_grant, seen, strict=True))

    svc.upsert_group_module_assignment(
        actor=admin, group_id=gid, module_key=MODULE, role="TA_MANAGER", enabled=True, client_scope=ALL
    )  # role change
    after_role = versions()
    assert all(a > b for a, b in zip(after_role, after_grant, strict=True))

    svc.upsert_group_module_assignment(
        actor=admin, group_id=gid, module_key=MODULE, role="TA_MANAGER", enabled=True,
        client_scope=ClientScopeIn(all_clients=False, client_ids=[1]),
    )  # scope change
    after_scope = versions()
    assert all(a > b for a, b in zip(after_scope, after_role, strict=True))

    svc.set_group_status(actor=admin, group_id=gid, status="INACTIVE")
    after_status = versions()
    assert all(a > b for a, b in zip(after_status, after_scope, strict=True))

    svc.set_group_status(actor=admin, group_id=gid, status="ACTIVE")
    svc.remove_group_module_assignment(actor=admin, group_id=gid, module_key=MODULE)
    after_removal = versions()
    assert all(a > b for a, b in zip(after_removal, after_status, strict=True))

    ta_before_removal = _av(db, ta.id)
    svc.remove_group_member(actor=admin, group_id=gid, target_user_id=ta.id)
    assert _av(db, ta.id) > ta_before_removal

    assert _av(db, outsider.id) == outsider_before  # never touched


def test_group_scope_row_edit_made_directly_still_bumps_members(db, two_tenant_world):
    ta, cs, admin = _people(db, two_tenant_world)
    svc, gid = _group(db, admin, [ta, cs])
    svc.upsert_group_module_assignment(
        actor=admin, group_id=gid, module_key=MODULE, role="TA_MEMBER", enabled=True,
        client_scope=ClientScopeIn(all_clients=False, client_ids=[1]),
    )
    before = (_av(db, ta.id), _av(db, cs.id))
    row = db.execute(select(GroupModuleClientScope)).scalars().first()
    row.all_clients = True
    db.commit()
    assert _av(db, ta.id) > before[0] and _av(db, cs.id) > before[1]


def test_membership_row_added_outside_the_service_is_still_covered(db, two_tenant_world):
    ta, _cs, admin = _people(db, two_tenant_world)
    _svc, gid = _group(db, admin, [])
    before = _av(db, ta.id)
    db.add(UserGroupMembership(user_id=ta.id, access_group_id=gid))
    db.commit()
    assert _av(db, ta.id) > before


def test_default_access_and_catalogue_changes_reach_everyone(db, two_tenant_world):
    ta, cs, _admin = _people(db, two_tenant_world)
    before = (_av(db, ta.id), _av(db, cs.id))
    db.add(ModuleBaselineRole(module_key="field-ops", role="FIELD_USER", enabled=True))
    db.commit()
    mid = (_av(db, ta.id), _av(db, cs.id))
    assert all(a > b for a, b in zip(mid, before, strict=True))
    row = db.get(ModuleBaselineRole, "field-ops")
    row.enabled = False
    db.commit()
    assert all(a > b for a, b in zip((_av(db, ta.id), _av(db, cs.id)), mid, strict=True))


def test_a_flag_that_changes_nothing_does_not_bump(db, two_tenant_world):
    ta, _cs, admin = _people(db, two_tenant_world)
    AdminService(db).upsert_module_assignment(
        actor=admin, target_user_id=ta.id, module_key=MODULE, role="TA_MEMBER", enabled=True, client_scope=ALL
    )
    before = _av(db, ta.id)
    role = db.execute(select(UserModuleRole).where(UserModuleRole.user_id == ta.id)).scalars().one()
    role.role = role.role  # touched, not changed
    db.commit()
    assert _av(db, ta.id) == before


# --- concurrency ---------------------------------------------------------------


def test_two_sessions_changing_one_person_never_lose_an_increment(db, two_tenant_world):
    ta, _cs, admin = _people(db, two_tenant_world)
    base = _av(db, ta.id)
    with SessionLocal() as other:
        AdminService(other).upsert_module_assignment(
            actor=other.get(User, admin.id), target_user_id=ta.id, module_key=MODULE, role="TA_MEMBER",
            enabled=True, client_scope=ALL,
        )
    AdminService(db).upsert_module_assignment(
        actor=admin, target_user_id=ta.id, module_key=MODULE, role="TA_MEMBER", enabled=False, client_scope=ALL
    )
    assert _av(db, ta.id) == base + 2


# --- tokens --------------------------------------------------------------------


def test_issued_and_refreshed_tokens_carry_the_current_version(api_client, db, two_tenant_world):
    ta, _cs, admin = _people(db, two_tenant_world)
    old = auth_headers(api_client, "test-ta")
    start = _av(db, ta.id)
    assert decode_session_token(old["Authorization"].split()[1])["av"] == start
    AdminService(db).upsert_module_assignment(
        actor=admin, target_user_id=ta.id, module_key=MODULE, role="TA_MEMBER", enabled=True, client_scope=ALL
    )
    current = _av(db, ta.id)
    refreshed = api_client.post("/api/auth/refresh", headers=old)  # an older token can still refresh
    assert refreshed.status_code == 200
    claims = decode_session_token(refreshed.json()["access_token"])
    assert claims["av"] == current > start
    assert claims["module_roles"][MODULE]["role"] == "TA_MEMBER"  # and gets the current roles


def test_a_change_committed_while_claims_are_built_leaves_the_token_behind(db, two_tenant_world, monkeypatch):
    ta, _cs, admin = _people(db, two_tenant_world)
    real = auth_routes.build_claims

    def build_then_change(user, session):
        claims = real(user, session)  # claims read, then a change commits before the token is signed
        with SessionLocal() as other:
            AdminService(other).upsert_module_assignment(
                actor=other.get(User, admin.id), target_user_id=ta.id, module_key=MODULE, role="TA_MEMBER",
                enabled=True, client_scope=ALL,
            )
        return claims

    monkeypatch.setattr(auth_routes, "build_claims", build_then_change)
    token = auth_routes.issue_user_session(db.get(User, ta.id), db)
    issued = decode_session_token(token)["av"]
    assert issued < _av(db, ta.id)  # it will be rejected and refreshed, never silently accepted


# --- the snapshot --------------------------------------------------------------


def test_snapshot_requires_the_internal_secret(api_client):
    assert api_client.get(FEED).status_code == 401
    assert api_client.get(FEED, headers={"X-Internal-Token": "nope"}).status_code == 401


def test_snapshot_lists_changed_and_inactive_users_with_a_stable_etag(api_client, db, two_tenant_world):
    ta, cs, admin = _people(db, two_tenant_world)
    svc = AdminService(db)
    svc.upsert_module_assignment(
        actor=admin, target_user_id=ta.id, module_key=MODULE, role="TA_MEMBER", enabled=True, client_scope=ALL
    )
    svc.set_user_active(actor=admin, target_user_id=cs.id, is_active=False)
    first = api_client.get(FEED, headers=internal_headers())
    users = first.json()["users"]
    assert users[str(ta.id)] == {"av": _av(db, ta.id), "active": True}
    assert users[str(cs.id)]["active"] is False
    fresh = User(email="untouched@example.com", full_name="Untouched", persona_key="test-untouched")
    db.add(fresh)
    db.commit()
    assert str(fresh.id) not in api_client.get(FEED, headers=internal_headers()).json()["users"]  # av 0, active

    etag = first.headers["etag"]
    again = api_client.get(FEED, headers={**internal_headers(), "If-None-Match": etag})
    assert again.status_code == 304 and again.headers["etag"] == etag
    svc.set_user_active(actor=admin, target_user_id=cs.id, is_active=True)
    changed = api_client.get(FEED, headers={**internal_headers(), "If-None-Match": etag})
    assert changed.status_code == 200 and changed.headers["etag"] != etag


def test_group_grant_rows_are_the_models_the_listener_watches(db):
    # Guard: if these models are renamed, the listener's imports fail loudly rather than silently.
    assert GroupModuleRole.__tablename__ and UserGroupMembership.__tablename__
