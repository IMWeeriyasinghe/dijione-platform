"""D2: users.access_version moves with every change that can alter access; tokens carry
the version they were issued under; the internal snapshot lists what applications need."""

import time
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.routes import auth as auth_routes
from app.core.security import decode_session_token
from app.db.session import SessionLocal
from app.models.access_group import (
    AccessGroup,
    GroupModuleClientScope,
    GroupModuleRole,
    UserGroupMembership,
)
from app.models.module_baseline import ModuleBaselineRole
from app.models.user import User, UserModuleRole
from app.models.user_module_client_scope import UserModuleClientScope
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
    after = _av(db, ta.id)
    assert after >= base + 2 and after > int(time.time()) - 5  # two distinct, ordered increments


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


# --- rows built through relationships (foreign keys not yet set at flush) -----------------


def test_assignments_built_through_relationships_are_covered(db, two_tenant_world):
    ta, cs, _admin = _people(db, two_tenant_world)
    before = _av(db, ta.id)
    ta_row = db.get(User, ta.id)
    ta_row.module_roles.append(UserModuleRole(module_key="spark", role="SPARK_USER"))  # no user_id set by hand
    db.commit()
    assert _av(db, ta.id) > before

    db.expire_all()
    role = db.execute(
        select(UserModuleRole).where(UserModuleRole.user_id == ta.id, UserModuleRole.module_key == "spark")
    ).scalars().one()
    mid = _av(db, ta.id)
    role.client_scopes.append(UserModuleClientScope(all_clients=True))  # scope via the parent, not its id
    db.commit()
    assert _av(db, ta.id) > mid


def test_group_grants_built_through_relationships_reach_members(db, two_tenant_world):
    ta, cs, admin = _people(db, two_tenant_world)
    _svc, gid = _group(db, admin, [ta, cs])
    before = (_av(db, ta.id), _av(db, cs.id))
    group = db.get(AccessGroup, gid)
    group.module_roles.append(GroupModuleRole(module_key=MODULE, role="TA_MEMBER"))
    db.commit()
    mid = (_av(db, ta.id), _av(db, cs.id))
    assert all(a > b for a, b in zip(mid, before, strict=True))
    grant = db.execute(select(GroupModuleRole).where(GroupModuleRole.access_group_id == gid)).scalars().one()
    grant.client_scopes.append(GroupModuleClientScope(all_clients=True))
    db.commit()
    assert all(a > b for a, b in zip((_av(db, ta.id), _av(db, cs.id)), mid, strict=True))


def test_deleting_a_group_invalidates_every_member_and_only_them(db, two_tenant_world):
    ta, cs, admin = _people(db, two_tenant_world)
    outsider = two_tenant_world["abc_user"]
    _svc, gid = _group(db, admin, [ta, cs], key="doomed")
    before = (_av(db, ta.id), _av(db, cs.id), _av(db, outsider.id))
    db.delete(db.get(AccessGroup, gid))
    db.commit()
    assert _av(db, ta.id) > before[0] and _av(db, cs.id) > before[1] and _av(db, outsider.id) == before[2]


def test_a_user_created_with_roles_in_one_step_does_not_break_the_flush(db, two_tenant_world):
    user = User(email="born@example.com", full_name="Born", persona_key="test-born")
    user.module_roles.append(UserModuleRole(module_key=MODULE, role="TA_MEMBER"))
    db.add(user)
    db.commit()  # no user id exists when the listener runs
    assert _av(db, user.id) == 0


# --- migrations bypass the session, so they must bump explicitly -------------------------------

ACCESS_TABLES = (
    "user_module_roles", "user_module_client_scopes", "group_module_roles", "group_module_client_scopes",
    "user_group_memberships", "access_groups", "module_baseline_roles", "application_modules",
    "roles", "role_permissions", "permissions",
)


def test_every_migration_after_access_version_that_changes_access_bumps_everyone():
    """An Alembic migration writes through the connection, not the session, so the listener never
    sees it. Any later migration that touches an access table must also bump every user's
    access_version (``UPDATE users SET access_version = access_version + 1``) or sessions keep
    their old permissions."""
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    scripts = ScriptDirectory.from_config(config)
    offenders = []
    for revision in scripts.walk_revisions():  # newest first
        if revision.revision == "h4j6k8m0n2p3":
            break
        text = Path(revision.path).read_text()
        if any(table in text for table in ACCESS_TABLES) and "access_version" not in text:
            offenders.append(revision.revision)
    assert offenders == [], f"migrations that change access without bumping access_version: {offenders}"


# --- the bump and the change are one transaction ------------------------------------------------


def test_a_rolled_back_change_leaves_the_version_alone(db, two_tenant_world):
    ta, _cs, _admin = _people(db, two_tenant_world)
    before = _av(db, ta.id)
    db.add(UserModuleRole(user_id=ta.id, module_key="spark", role="SPARK_USER"))
    db.flush()  # the bump and the new row are written, uncommitted
    db.rollback()
    assert _av(db, ta.id) == before
    assert db.execute(
        select(UserModuleRole).where(UserModuleRole.user_id == ta.id, UserModuleRole.module_key == "spark")
    ).first() is None


def test_a_failed_flush_does_not_leave_a_bump_behind(db, two_tenant_world):
    import pytest
    from sqlalchemy.exc import IntegrityError

    ta, _cs, _admin = _people(db, two_tenant_world)
    before = _av(db, ta.id)
    db.add(UserModuleRole(user_id=ta.id, module_key=MODULE, role="TA_MEMBER"))  # one per user and application
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
    assert _av(db, ta.id) == before


def test_a_change_and_its_bump_are_visible_together_after_commit(db, two_tenant_world):
    ta, _cs, admin = _people(db, two_tenant_world)
    before = _av(db, ta.id)
    AdminService(db).upsert_module_assignment(
        actor=admin, target_user_id=ta.id, module_key=MODULE, role="TA_MANAGER", enabled=True, client_scope=ALL
    )
    with SessionLocal() as other:  # a different connection, as another request would see it
        version = other.execute(select(User.access_version).where(User.id == ta.id)).scalar_one()
        role = other.execute(
            select(UserModuleRole.role).where(UserModuleRole.user_id == ta.id, UserModuleRole.module_key == MODULE)
        ).scalar_one()
    assert version > before and role == "TA_MANAGER"


# --- refresh never trusts what the old token says about itself -----------------------------------


def test_refresh_takes_the_version_and_roles_from_the_database_not_the_token(api_client, db, two_tenant_world):
    from tests.test_session_refresh import _forge

    ta = two_tenant_world["ta_user"]
    current = _av(db, ta.id)
    forged = {"Authorization": "Bearer " + _forge(ta, av=10_000, module_roles={"talent-flow": {"role": "TA_MANAGER"}})}
    resp = api_client.post("/api/auth/refresh", headers=forged)
    assert resp.status_code == 200
    claims = decode_session_token(resp.json()["access_token"])
    assert claims["av"] == current  # not 10_000: a token cannot award itself a version
    assert claims["module_roles"][MODULE]["role"] != "TA_MANAGER"  # nor roles it was not granted


def test_a_session_revoked_by_a_group_change_refreshes_into_current_access(api_client, db, two_tenant_world):
    ta, cs, admin = _people(db, two_tenant_world)
    old = auth_headers(api_client, "test-ta")
    svc, gid = _group(db, admin, [ta, cs])
    svc.upsert_group_module_assignment(
        actor=admin, group_id=gid, module_key="birthday", role="BIRTHDAY_USER", enabled=True, client_scope=ALL
    )
    old_av = decode_session_token(old["Authorization"].split()[1])["av"]
    assert old_av < _av(db, ta.id)  # the old token is now revoked
    resp = api_client.post("/api/auth/refresh", headers=old)
    assert resp.status_code == 200
    fresh = decode_session_token(resp.json()["access_token"])
    assert fresh["av"] == _av(db, ta.id) and "birthday" in fresh["module_roles"]


def test_a_deactivated_account_is_refused_even_with_a_current_version(api_client, db, two_tenant_world):
    ta, _cs, admin = _people(db, two_tenant_world)
    token = auth_headers(api_client, "test-ta")
    AdminService(db).set_user_active(actor=admin, target_user_id=ta.id, is_active=False)
    assert api_client.post("/api/auth/refresh", headers=token).status_code == 401


# --- a database restore must not let a new revocation reuse an old number --------------------------


def test_a_bump_is_never_below_the_current_time(db, two_tenant_world):
    ta, _cs, admin = _people(db, two_tenant_world)
    AdminService(db).set_user_active(actor=admin, target_user_id=ta.id, is_active=False)
    assert _av(db, ta.id) >= int(time.time()) - 5


def test_after_a_restore_a_new_revocation_still_outranks_tokens_issued_before_it(db, two_tenant_world, monkeypatch):
    """The database is restored to an earlier state, so its counter is low, while sessions
    issued in the lost interval carry the higher number they were given. A plain +1 would
    land below them and the revocation would not touch them."""
    ta, _cs, admin = _people(db, two_tenant_world)
    AdminService(db).set_user_active(actor=admin, target_user_id=ta.id, is_active=False)
    issued_before_the_restore = _av(db, ta.id)
    db.execute(update(User).where(User.id == ta.id).values(access_version=3))  # the restored counter
    db.commit()
    later = time.time() + 3600  # an hour on: restoring a backup takes at least that long to notice and do
    monkeypatch.setattr("app.services.access_version.time.time", lambda: later)
    AdminService(db).set_user_active(actor=admin, target_user_id=ta.id, is_active=True)
    assert _av(db, ta.id) > issued_before_the_restore


def test_the_post_restore_command_revokes_every_older_session(db, two_tenant_world):
    from app.services.access_version import bump_all

    ta, cs, _admin = _people(db, two_tenant_world)
    db.execute(update(User).values(access_version=7))  # a restored database
    db.commit()
    with db.begin_nested():
        assert bump_all(db.connection()) >= 2
    db.commit()
    assert _av(db, ta.id) >= int(time.time()) - 5 and _av(db, cs.id) >= int(time.time()) - 5


def test_the_access_version_column_is_wide_enough_for_unix_time():
    assert User.__table__.c.access_version.type.__class__.__name__ == "BigInteger"
