"""View-as: a SUPER_ADMIN's read-only simulation of an internal employee."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.security import SESSION_ACTOR_VIEW_AS, decode_session_token
from app.models.audit_log import AuditLog
from app.models.user import User
from app.models.view_as_session import ViewAsSession
from app.schemas.admin import ClientScopeIn
from app.services.admin_service import AdminService
from app.services.claims_service import build_claims
from tests.conftest import auth_headers

START = "/api/platform/admin/view-as"


@pytest.fixture()
def world(db, two_tenant_world):
    """The employee to be viewed is an internal employee, as only a verified Microsoft sign-in makes one."""
    ta = db.get(User, two_tenant_world["ta_user"].id)
    ta.internal_employee = True
    db.commit()
    return two_tenant_world


def _start(api_client, who, target_id):
    return api_client.post(START, json={"target_user_id": target_id}, headers=auth_headers(api_client, who))


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _started(api_client, world):
    resp = _start(api_client, "test-super-admin", world["ta_user"].id)
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- who may start -------------------------------------------------------------------------------


def test_only_a_super_admin_with_the_permission_may_start(api_client, world):
    target = world["ta_user"].id
    assert _start(api_client, "test-super-admin", target).status_code == 201
    assert _start(api_client, "test-platform-admin", target).status_code == 403  # an administrator, not SUPER_ADMIN
    assert _start(api_client, "test-ta", target).status_code == 403
    assert api_client.post(START, json={"target_user_id": target}).status_code in (401, 403)


def test_the_permission_is_held_by_the_super_admin_role_only(db, world):
    from app.services.authorization_service import AuthorizationService

    authz = AuthorizationService(db)
    assert "platform.admin.view_as" in authz.platform_permissions(world["super_admin"])
    assert "platform.admin.view_as" not in authz.platform_permissions(world["platform_admin"])


def test_a_super_admin_whose_permission_is_missing_is_refused_even_with_the_role(db, world, monkeypatch, api_client):
    from app.services import view_as_service

    monkeypatch.setattr(view_as_service, "PERMISSION", "platform.admin.no_such_permission")
    assert _start(api_client, "test-super-admin", world["ta_user"].id).status_code == 403


# --- who may be viewed ---------------------------------------------------------------------------


def test_only_an_active_internal_employee_other_than_oneself_can_be_viewed(db, world, api_client):
    outcomes = {
        "self": _start(api_client, "test-super-admin", world["super_admin"].id),
        "unknown": _start(api_client, "test-super-admin", 99999),
        "not internal": _start(api_client, "test-super-admin", world["cs_user"].id),
    }
    inactive = db.get(User, world["ta_user"].id)
    inactive.is_active = False
    db.commit()
    outcomes["inactive"] = _start(api_client, "test-super-admin", inactive.id)
    assert {r.status_code for r in outcomes.values()} == {404}
    assert len({r.json()["detail"] for r in outcomes.values()}) == 1  # one answer, whatever the reason


def test_a_supplier_portal_identity_is_not_a_viewable_user(api_client, world):
    # Supplier users are not DijiOne users at all: there is no id to choose, and no token for them is minted.
    assert _start(api_client, "test-super-admin", 10_000_001).status_code == 404


# --- the token ---------------------------------------------------------------------------------------


def test_the_token_is_signed_for_the_employee_and_marked_as_view_as(db, world, api_client):
    started = _started(api_client, world)
    claims = decode_session_token(started["access_token"])
    target = db.get(User, world["ta_user"].id)
    assert claims["sub"] == str(target.id) and claims["actor_type"] == SESSION_ACTOR_VIEW_AS
    assert claims["module_roles"] == build_claims(target, db)["module_roles"]  # exactly the employee's access
    assert claims["view_as"]["session_id"] == started["session_id"]
    assert claims["view_as"]["actor_id"] == world["super_admin"].id
    assert "sst" not in claims  # not a sign-in: nothing to refresh from
    ttl = datetime.fromtimestamp(claims["exp"], UTC) - datetime.now(UTC)
    assert timedelta(minutes=25) < ttl <= timedelta(minutes=30)


def test_the_token_is_refused_everywhere_a_staff_session_is_needed(api_client, world):
    token = _bearer(_started(api_client, world)["access_token"])
    for method, path in (
        ("post", "/api/auth/refresh"),  # cannot be turned into a normal, refreshable session
        ("get", "/api/platform/admin/users"),
        ("get", "/api/platform/admin/audit"),
        ("post", "/api/notifications/1/read"),
        ("post", START),
        ("post", f"{START}/anything/end"),
    ):
        resp = getattr(api_client, method)(path, headers=token, **({"json": {"target_user_id": 1}} if path == START else {}))
        assert resp.status_code == 403 and resp.headers["x-auth-error"] == "view_as_read_only", (method, path)


def test_a_staff_session_cannot_pass_itself_off_as_view_as_or_the_reverse(api_client, world):
    staff = auth_headers(api_client, "test-super-admin")
    assert api_client.get("/api/auth/me", headers=staff).json()["view_as"] is None


# --- what a shell can read in a session ----------------------------------------------------------------


def test_me_modules_and_notifications_answer_for_the_employee_with_the_banner_facts(db, world, api_client):
    started = _started(api_client, world)
    token = _bearer(started["access_token"])
    me = api_client.get("/api/auth/me", headers=token).json()
    assert me["id"] == world["ta_user"].id and me["email"] == "ta-user@example.com"
    assert me["view_as"]["session_id"] == started["session_id"]
    assert me["view_as"]["actor_name"] == "Super Admin" and me["view_as"]["read_only"] is True
    assert api_client.get("/api/modules", headers=token).status_code == 200
    assert api_client.get("/api/notifications", headers=token).status_code == 200


# --- ending, expiry and everything that invalidates a session ------------------------------------------


def test_ending_a_session_ends_it_at_once_and_is_audited(db, world, api_client):
    started = _started(api_client, world)
    token = _bearer(started["access_token"])
    admin = auth_headers(api_client, "test-super-admin")
    assert api_client.post(f"{START}/{started['session_id']}/end", headers=admin).json() == {
        "session_id": started["session_id"], "ended": True,
    }
    gone = api_client.get("/api/auth/me", headers=token)
    assert gone.status_code == 401 and gone.headers["x-auth-error"] == "view_as_ended"
    assert api_client.post(f"{START}/{started['session_id']}/end", headers=admin).status_code == 200  # idempotent

    db.expire_all()
    actions = [
        a.action for a in db.execute(select(AuditLog).where(AuditLog.subject_user_id == world["ta_user"].id)).scalars()
        if a.action.startswith("view_as.")
    ]
    assert actions.count("view_as.started") == 1 and actions.count("view_as.ended") == 1  # ended twice, audited once
    started_row = db.execute(select(AuditLog).where(AuditLog.action == "view_as.started")).scalars().one()
    assert started_row.actor_id == world["super_admin"].id and started_row.subject_user_id == world["ta_user"].id


def test_only_the_administrator_who_started_a_session_can_end_it(api_client, world):
    started = _started(api_client, world)
    other = auth_headers(api_client, "test-platform-admin")
    assert api_client.post(f"{START}/{started['session_id']}/end", headers=other).status_code == 404


def test_starting_another_session_ends_the_previous_one(db, world, api_client):
    first = _started(api_client, world)
    second = _started(api_client, world)
    assert api_client.get("/api/auth/me", headers=_bearer(first["access_token"])).status_code == 401
    assert api_client.get("/api/auth/me", headers=_bearer(second["access_token"])).status_code == 200
    reasons = {s.end_reason for s in db.execute(select(ViewAsSession)).scalars() if s.ended_at}
    assert reasons == {"replaced"}


def test_an_expired_session_stops_working(db, world, api_client):
    started = _started(api_client, world)
    row = db.execute(select(ViewAsSession)).scalars().one()
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert api_client.get("/api/auth/me", headers=_bearer(started["access_token"])).status_code == 401


def test_a_change_to_the_employees_access_ends_the_session(db, world, api_client):
    started = _started(api_client, world)
    db.get(User, world["ta_user"].id).full_name = "Renamed"  # a display name is not an access change
    db.commit()
    assert api_client.get("/api/auth/me", headers=_bearer(started["access_token"])).status_code == 200
    AdminService(db).upsert_module_assignment(
        actor=world["super_admin"], target_user_id=world["ta_user"].id, module_key="talent-flow", role="TA_MANAGER",
        enabled=True, client_scope=ClientScopeIn(all_clients=True),
    )
    assert api_client.get("/api/auth/me", headers=_bearer(started["access_token"])).status_code == 401


def test_deactivating_the_employee_ends_the_session(db, world, api_client):
    started = _started(api_client, world)
    AdminService(db).set_user_active(actor=world["super_admin"], target_user_id=world["ta_user"].id, is_active=False)
    assert api_client.get("/api/auth/me", headers=_bearer(started["access_token"])).status_code == 401


def test_demoting_or_deactivating_the_administrator_ends_the_session(db, world, api_client):
    started = _started(api_client, world)
    db.get(User, world["super_admin"].id).platform_role = "PLATFORM_ADMIN"
    db.commit()
    assert api_client.get("/api/auth/me", headers=_bearer(started["access_token"])).status_code == 401


def test_a_token_naming_someone_elses_session_is_refused(db, world, api_client):
    from app.core.security import issue_view_as_token

    started = _started(api_client, world)
    forged = issue_view_as_token(
        world["cs_user"].id, is_active=True, email="cs-user@example.com", full_name="CS", platform_role="PLATFORM_USER",
        platform_permissions=[], module_roles={}, av=0,
        exp=datetime.now(UTC) + timedelta(minutes=5),
        view_as={"session_id": started["session_id"], "actor_id": world["super_admin"].id, "actor_name": "x", "actor_av": 0},
    )
    assert api_client.get("/api/auth/me", headers=_bearer(forged)).status_code == 401  # session is for another employee
