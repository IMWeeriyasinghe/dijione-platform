"""Module registry visibility (CLAUDE.md §9-10; Phase 2 CR §5, §58
Scenario 6): COMING_SOON placeholder modules with no ``required_roles``
must be visible to every authenticated platform user (they are inert
teaser cards, not functional access to gate), while modules that do
require a role are only visible to users holding an *enabled* assignment
for that module.
"""

from app.core.constants import MODULE_BIRTHDAY, MODULE_TALENT_FLOW
from app.models.module import ApplicationModule
from tests.conftest import auth_headers


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
