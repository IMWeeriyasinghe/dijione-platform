"""Seeds Platform Core's local demo data: the Role/Permission catalog, the
module registry, dev personas, module-role assignments and client/portfolio
scope.

Run with:  python scripts/seed.py [--reset]

Phase 2.5 note — coordinated seeding across services: DijiTalentFlow's
Client rows now live in talent-api's own database, so this script can't
create them or look up their ids. The module-role/client-scope rows below
reference client ids 1 (ABC Company), 2 (XYZ Company), 3 (Nova Solutions) by
plain integer convention — ``apps/talent-api/scripts/seed.py`` creates those
three clients in that exact order so a fresh ``--reset`` reseed of both
services lines up. Run this script *before* talent-api's, since talent-api's
seed data (requests, messages, documents) references the user ids created
here (also by convention: madushanka=1, cs_user=2, ta_manager=3,
platform_admin=4, super_admin=5, abc_client=6, xyz_client=7, nova_client=8,
ta_portfolio=9). See docs/platform/local-development.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.constants import MODULE_BIRTHDAY, MODULE_SPARK, MODULE_TALENT_FLOW, PlatformRole  # noqa: E402
from app.core.permissions import ALL_PERMISSIONS, ALL_ROLES  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.module import ApplicationModule  # noqa: E402
from app.models.role import Permission, Role, RolePermission  # noqa: E402
from app.models.user import User, UserModuleRole  # noqa: E402
from app.models.user_module_client_scope import UserModuleClientScope  # noqa: E402

# Client id convention shared with apps/talent-api/scripts/seed.py — see
# module docstring.
ABC_CLIENT_ID = 1
XYZ_CLIENT_ID = 2
NOVA_CLIENT_ID = 3


def reset_schema() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def seed_authorization_catalog(db) -> None:
    """Populate the Role / Permission / RolePermission catalog from the
    single source of truth in ``app.core.permissions``. Mirrors the Alembic
    migration's backfill so a fresh ``--reset`` reseed and a migrated
    existing database end up identical.
    """
    permission_ids: dict[str, int] = {}
    for perm in ALL_PERMISSIONS:
        row = Permission(
            key=perm.key, name=perm.name, description=perm.description,
            module_key=perm.module_key, category=perm.category,
        )
        db.add(row)
        db.flush()
        permission_ids[perm.key] = row.id

    for role_def in ALL_ROLES:
        role = Role(
            module_key=role_def.module_key, key=role_def.key, name=role_def.name,
            description=role_def.description, is_system=True,
        )
        db.add(role)
        db.flush()
        for perm_key in role_def.permissions:
            db.add(RolePermission(role_id=role.id, permission_id=permission_ids[perm_key]))
    db.commit()


def _assign_client_scope(db, module_role: UserModuleRole, *, client_id: int | None) -> None:
    if client_id is not None:
        db.add(UserModuleClientScope(user_module_role_id=module_role.id, client_id=client_id, all_clients=False))
    else:
        db.add(UserModuleClientScope(user_module_role_id=module_role.id, all_clients=True))


def seed() -> None:
    db = SessionLocal()
    try:
        seed_authorization_catalog(db)

        # --- Module registry --------------------------------------------
        db.add_all(
            [
                ApplicationModule(
                    key=MODULE_TALENT_FLOW,
                    name="DijiTalentFlow",
                    description="Talent Operations and Client Tracking",
                    icon="Users",
                    route="/talent-flow",
                    status="ACTIVE",
                    enabled=True,
                    display_order=1,
                    required_roles="ANY",
                ),
                ApplicationModule(
                    key=MODULE_BIRTHDAY,
                    name="DijiBirthday",
                    description="Birthday Workflow Automation",
                    icon="Cake",
                    route="/birthday",
                    status="COMING_SOON",
                    enabled=True,
                    display_order=2,
                    # Empty = visible to every authenticated platform user.
                    # Coming Soon cards are inert teasers with no functional
                    # access to gate, unlike DijiTalentFlow above which
                    # requires an actual module assignment.
                    required_roles="",
                ),
                ApplicationModule(
                    key=MODULE_SPARK,
                    name="DijiSpark",
                    description="HR / Spark Hire Workflows",
                    icon="Sparkles",
                    route="/spark",
                    status="COMING_SOON",
                    enabled=True,
                    display_order=3,
                    required_roles="",
                ),
            ]
        )
        db.commit()

        # --- Users / dev personas -----------------------------------------
        madushanka = User(
            email="madushanka@dijitalteam.com", full_name="Madushanka Weeriyasinghe",
            title="Talent Acquisition Specialist", platform_role=PlatformRole.PLATFORM_USER.value,
            persona_key="madushanka-ta", avatar_color="#c9431d",
        )
        cs_user = User(
            email="tharindu.fernando@dijitalteam.com", full_name="Tharindu Fernando",
            title="Customer Success Lead", platform_role=PlatformRole.PLATFORM_USER.value,
            persona_key="customer-success", avatar_color="#db4d18",
        )
        ta_manager = User(
            email="sanduni.wickrama@dijitalteam.com", full_name="Sanduni Wickrama",
            title="TA Manager", platform_role=PlatformRole.PLATFORM_USER.value,
            persona_key="ta-manager", avatar_color="#aa2f1d",
        )
        platform_admin = User(
            email="admin@dijitalteam.com", full_name="Dilani Rathnayake",
            title="Platform Administrator", platform_role=PlatformRole.PLATFORM_ADMIN.value,
            persona_key="platform-admin", avatar_color="#8f2417",
        )
        super_admin = User(
            email="superadmin@dijitalteam.com", full_name="Priyantha Bandara",
            title="DijiOne Super Admin", platform_role=PlatformRole.SUPER_ADMIN.value,
            persona_key="super-admin", avatar_color="#5c1a15",
        )
        abc_client_user = User(
            email="amal.perera@abc-company.example", full_name="Amal Perera",
            title="Head of Talent, ABC Company", platform_role=PlatformRole.PLATFORM_USER.value,
            persona_key="abc-client", avatar_color="#f26a1b",
        )
        xyz_client_user = User(
            email="nadeesha.silva@xyz-company.example", full_name="Nadeesha Silva",
            title="VP Engineering, XYZ Company", platform_role=PlatformRole.PLATFORM_USER.value,
            persona_key="xyz-client", avatar_color="#f59e0b",
        )
        nova_client_user = User(
            email="kasun.jayasuriya@nova-solutions.example", full_name="Kasun Jayasuriya",
            title="COO, Nova Solutions", platform_role=PlatformRole.PLATFORM_USER.value,
            persona_key="nova-client", avatar_color="#fbc34a",
        )
        ta_portfolio_user = User(
            email="ruwan.gunasekara@dijitalteam.com", full_name="Ruwan Gunasekara",
            title="Talent Acquisition Specialist (ABC + XYZ Portfolio)",
            platform_role=PlatformRole.PLATFORM_USER.value,
            persona_key="ta-portfolio", avatar_color="#f26a1b",
        )
        db.add_all(
            [
                madushanka, cs_user, ta_manager, platform_admin, super_admin,
                abc_client_user, xyz_client_user, nova_client_user, ta_portfolio_user,
            ]
        )
        db.flush()

        # Demonstrates DijiOne Phase 2 client/portfolio scope (CR §22): every
        # staff assignment defaults to ALL_CLIENTS except ta_portfolio_user,
        # who is explicitly restricted to ABC + XYZ (Nova excluded).
        module_roles = [
            (madushanka, "TA_MEMBER", None, None),
            (cs_user, "CUSTOMER_SUCCESS", None, None),
            (ta_manager, "TA_MANAGER", None, None),
            (platform_admin, "TA_MANAGER", None, None),
            (abc_client_user, "TALENT_CLIENT", ABC_CLIENT_ID, None),
            (xyz_client_user, "TALENT_CLIENT", XYZ_CLIENT_ID, None),
            (nova_client_user, "TALENT_CLIENT", NOVA_CLIENT_ID, None),
            (ta_portfolio_user, "TA_MEMBER", None, [ABC_CLIENT_ID, XYZ_CLIENT_ID]),
        ]
        for user, role, client_id, portfolio in module_roles:
            module_role = UserModuleRole(
                user_id=user.id, module_key=MODULE_TALENT_FLOW, role=role, client_id=client_id,
            )
            db.add(module_role)
            db.flush()
            if portfolio is not None:
                for portfolio_client_id in portfolio:
                    _assign_client_scope(db, module_role, client_id=portfolio_client_id)
            else:
                _assign_client_scope(db, module_role, client_id=client_id)
        db.commit()

        print("Platform Core seed complete.")
        print(
            "  Dev personas: madushanka-ta, customer-success, ta-manager, "
            "platform-admin, super-admin, abc-client, xyz-client, nova-client, "
            "ta-portfolio (ABC+XYZ only)"
        )
        print("  Now run: (cd ../talent-api && python scripts/seed.py [--reset])")
    finally:
        db.close()


if __name__ == "__main__":
    if "--reset" in sys.argv:
        reset_schema()
    seed()
