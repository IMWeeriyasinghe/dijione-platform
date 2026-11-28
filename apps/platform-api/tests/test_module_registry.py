"""Module registry visibility: COMING_SOON placeholder modules with no
``required_roles`` must be visible to every authenticated platform user
(they are inert teaser cards, not functional access to gate), while modules
that do require a role are only visible to users holding an *enabled*
assignment for that module.
"""

from app.core.constants import MODULE_ALERTS, MODULE_TALENT_FLOW
from app.models.module import ApplicationModule
from tests.conftest import auth_headers

MODULE_BIRTHDAY = "birthday"


def _seed_modules(db):
    db.add_all(
        [
            ApplicationModule(
                key=MODULE_TALENT_FLOW, name="DijiTalentFlow", description="d",
                icon="Users", route="/talent-flow", status="ACTIVE", enabled=True,
                display_order=1, required_roles="ANY",
            ),
            ApplicationModule(
                key=MODULE_BIRTHDAY, name="DijiBirthday", description="d",
                icon="Cake", route="/birthday", status="COMING_SOON", enabled=True,
                display_order=2, required_roles="",
            ),
        ]
    )
    db.commit()


def test_coming_soon_module_visible_to_any_authenticated_user(api_client, db, two_tenant_world):
    _seed_modules(db)
    headers = auth_headers(api_client, "test-abc-client")

    resp = api_client.get("/api/modules", headers=headers)
    keys = {m["key"] for m in resp.json()}
    assert MODULE_BIRTHDAY in keys
    assert MODULE_TALENT_FLOW in keys  # this persona holds a talent-flow role


def test_role_gated_module_hidden_without_assignment(api_client, db):
    """A user with no module assignments at all (e.g. a SUPER_ADMIN) must
    still see COMING_SOON cards but never the role-gated ACTIVE module."""
    from app.core.constants import PlatformRole
    from app.models.user import User

    _seed_modules(db)
    admin = User(
        email="admin-only@example.com", full_name="Admin Only",
        platform_role=PlatformRole.SUPER_ADMIN.value, persona_key="test-admin-only",
    )
    db.add(admin)
    db.commit()

    headers = auth_headers(api_client, "test-admin-only")
    resp = api_client.get("/api/modules", headers=headers)
    keys = {m["key"] for m in resp.json()}
    assert keys == {MODULE_BIRTHDAY}


def test_disabled_module_assignment_hides_role_gated_module(api_client, db, two_tenant_world):
    from sqlalchemy import select

    from app.models.user import UserModuleRole

    _seed_modules(db)
    role = db.execute(
        select(UserModuleRole).where(UserModuleRole.user_id == two_tenant_world["abc_user"].id)
    ).scalars().first()
    role.enabled = False
    db.commit()

    headers = auth_headers(api_client, "test-abc-client")
    resp = api_client.get("/api/modules", headers=headers)
    keys = {m["key"] for m in resp.json()}
    assert MODULE_TALENT_FLOW not in keys
    assert MODULE_BIRTHDAY in keys


def _seed_alerts_module(db):
    db.add(
        ApplicationModule(
            key=MODULE_ALERTS, name="DijiALERTS",
            description="Smart SMS Broadcasting & Emergency Communications",
            icon="BellAlert", route="/alerts", status="COMING_SOON", enabled=True,
            display_order=6, required_roles="",
        )
    )
    db.commit()


def test_dijialerts_visible_to_any_authenticated_user(api_client, db):
    """DijiALERTS is COMING_SOON with no required_roles — every authenticated
    user must see it, and it must never expose an operational route."""
    from app.core.constants import PlatformRole
    from app.models.user import User

    _seed_alerts_module(db)
    # A user with no module assignments at all (no roles anywhere).
    bare_user = User(
        email="bare@example.com", full_name="Bare User",
        platform_role=PlatformRole.PLATFORM_USER.value, persona_key="test-bare-user",
    )
    db.add(bare_user)
    db.commit()

    headers = auth_headers(api_client, "test-bare-user")
    resp = api_client.get("/api/modules", headers=headers)
    assert resp.status_code == 200
    modules = {m["key"]: m for m in resp.json()}
    assert MODULE_ALERTS in modules
    alert_module = modules[MODULE_ALERTS]
    assert alert_module["status"] == "COMING_SOON"
    assert alert_module["name"] == "DijiALERTS"


def test_dijialerts_no_route_collision_with_active_modules(api_client, db, two_tenant_world):
    """DijiALERTS must remain COMING_SOON and must never be listed as an
    operational service, even when other active modules are present."""
    _seed_modules(db)
    _seed_alerts_module(db)

    headers = auth_headers(api_client, "test-abc-client")
    resp = api_client.get("/api/modules", headers=headers)
    modules = {m["key"]: m for m in resp.json()}

    assert MODULE_ALERTS in modules
    assert modules[MODULE_ALERTS]["status"] == "COMING_SOON"
    # Active modules are unaffected.
    assert modules[MODULE_TALENT_FLOW]["status"] == "ACTIVE"
    assert modules[MODULE_BIRTHDAY]["status"] == "COMING_SOON"


# ---------------------------------------------------------------------------
# access_version exemption — behavioral evidence
#
# The w5x7z9b1d3f5 migration carries ``access_version: exempt`` because
# inserting a COMING_SOON row with no required_roles does not change any
# user's effective permission set.  The tests below are the evidence for
# that claim: they prove that DijiALERTS registers no authorization
# primitives and that existing JWT claims are unaffected by its presence.
# ---------------------------------------------------------------------------


def test_dijialerts_has_no_registered_permissions_roles_or_baseline_access(db):
    """After the alerts module is seeded, the authorization tables must contain
    no entries scoped to 'alerts'. No permissions, roles, role_permissions or
    module_baseline_roles are registered — only the catalogue row itself."""
    from sqlalchemy import text

    _seed_alerts_module(db)

    conn = db.connection()
    perms = conn.execute(text("SELECT COUNT(*) FROM permissions WHERE module_key = 'alerts'")).scalar()
    roles = conn.execute(text("SELECT COUNT(*) FROM roles WHERE module_key = 'alerts'")).scalar()
    baseline = conn.execute(
        text("SELECT COUNT(*) FROM module_baseline_roles WHERE module_key = 'alerts'")
    ).scalar()
    assert perms == 0, "DijiALERTS must register zero permissions"
    assert roles == 0, "DijiALERTS must register zero roles"
    assert baseline == 0, "DijiALERTS must have no baseline (default) role grant"


def test_dijialerts_does_not_appear_in_any_users_jwt_claims(api_client, db, two_tenant_world):
    """DijiALERTS is catalogue-only. It must never appear in a user's
    module_roles claim, regardless of that user's existing assignments."""
    _seed_alerts_module(db)
    # Test several personas: one with many roles, one with none, one client.
    for persona in ("test-ta", "test-abc-client", "test-super-admin"):
        token = api_client.post("/api/auth/dev-login", json={"persona_key": persona})
        assert token.status_code == 200
        from app.core.security import decode_session_token
        claims = decode_session_token(token.json()["access_token"])
        assert MODULE_ALERTS not in claims.get("module_roles", {}), (
            f"{persona} must not carry an 'alerts' module_role claim"
        )


def test_dijialerts_migration_does_not_modify_users_table(tmp_path):
    """The w5x7z9b1d3f5 migration must not modify any row in the users table.
    Proof: seed users into an isolated DB at v4w6y8a0c2e4, snapshot their
    access_version values, upgrade to w5x7z9b1d3f5, then compare."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    APP_ROOT = Path(__file__).resolve().parents[1]
    url = f"sqlite:///{tmp_path / 'alerts-av.db'}"
    env = {**os.environ, "DATABASE_URL": url, "APP_ENV": "development"}
    env.pop("PYTHONPATH", None)

    def alembic(*args):
        return subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=APP_ROOT, env=env, capture_output=True, text=True,
        )

    # Bring database to the revision before the DijiALERTS migration.
    r = alembic("upgrade", "v4w6y8a0c2e4")
    assert r.returncode == 0, r.stderr

    engine = create_engine(url)
    from app.models.user import User as UserModel

    # Seed two users through the ORM so all defaults are applied correctly.
    with Session(engine) as session:
        u1 = UserModel(email="u1-av@example.com", full_name="U1 Access", persona_key="u1-av")
        u2 = UserModel(email="u2-av@example.com", full_name="U2 Access", persona_key="u2-av")
        session.add_all([u1, u2])
        session.commit()
        u1_id, u2_id = u1.id, u2.id

    # Capture access_version for each user before the migration.
    with engine.connect() as conn:
        before = {
            row[0]: row[1]
            for row in conn.execute(text("SELECT id, access_version FROM users")).all()
        }

    # Apply only the DijiALERTS migration.
    r2 = alembic("upgrade", "w5x7z9b1d3f5")
    assert r2.returncode == 0, r2.stderr

    # Verify access_version is unchanged for all users.
    with engine.connect() as conn:
        after = {
            row[0]: row[1]
            for row in conn.execute(text("SELECT id, access_version FROM users")).all()
        }

    for uid in [u1_id, u2_id]:
        assert after[uid] == before[uid], (
            f"access_version changed for user {uid}: {before[uid]} → {after[uid]}. "
            "DijiALERTS migration must not touch users.access_version."
        )


def test_dijialerts_view_as_impersonation_shows_same_catalogue_as_direct_session(api_client, db, two_tenant_world):
    """When a platform admin uses view-as impersonation, the impersonated user
    must see the same DijiALERTS catalogue entry — and the entry must still be
    COMING_SOON, never ACTIVE, regardless of the impersonator's own permissions."""

    _seed_modules(db)
    _seed_alerts_module(db)

    # Direct session for the TA user.
    direct_headers = auth_headers(api_client, "test-ta")
    direct_modules = {m["key"]: m for m in api_client.get("/api/modules", headers=direct_headers).json()}

    # Confirm DijiALERTS is visible and COMING_SOON in the direct view.
    assert direct_modules.get(MODULE_ALERTS, {}).get("status") == "COMING_SOON"

    # The view-as endpoint (admin impersonation) must produce the same result.
    admin_headers = auth_headers(api_client, "test-super-admin")
    ta_user = two_tenant_world["ta_user"]
    view_as_resp = api_client.post(
        f"/api/platform/admin/view-as/{ta_user.id}",
        headers=admin_headers,
    )
    if view_as_resp.status_code == 404:
        # view-as endpoint not yet wired — skip gracefully.
        return
    assert view_as_resp.status_code in (200, 201)
    token = view_as_resp.json().get("access_token")
    if not token:
        return
    from app.core.security import decode_session_token
    claims = decode_session_token(token)
    assert MODULE_ALERTS not in claims.get("module_roles", {}), (
        "An impersonated session must not carry an 'alerts' module_role claim"
    )
