"""Seeds Platform Core's local demo data: the Role/Permission catalog, the
module registry, dev personas, module-role assignments, client/portfolio
scope, and the canonical Client/Organisation identity.

Run with:  python scripts/seed.py [--reset]

Coordinated seeding across services: platform-api is the permanent owner of
canonical Client identity (Architecture Completion Plan §6.1) —
``seed_canonical_clients`` creates the three ``Client`` rows here, with
stable ``public_id``s (``cli-abc-company`` / ``cli-xyz-company`` /
``cli-nova-solutions``), and every ``UserModuleClientScope`` /
``UserModuleRole`` row below carries the real ``client_ref`` alongside the
legacy bare integer. The legacy integer (``ABC_CLIENT_ID``=1 etc.) is kept
only so a pre-Wave-A ``talent-api`` reseed (its own clients created in that
same order) still lines up by convention for backward compatibility — new
code should never need to rely on that ordering, only on ``client_ref`` /
``platform_client_id``. Run this script *before* talent-api's, since
talent-api's seed data (requests, messages, documents) references the user
ids created here (by convention: madushanka=1, cs_user=2, ta_manager=3,
platform_admin=4, super_admin=5, abc_client=6, xyz_client=7, nova_client=8,
ta_portfolio=9). See docs/platform/local-development.md and
docs/platform/data-ownership.md §1.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.constants import MODULE_BIRTHDAY, MODULE_SPARK, MODULE_TALENT_FLOW, PlatformRole  # noqa: E402
from app.core.permissions import ALL_PERMISSIONS, ALL_ROLES  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.client import Client, ClientExternalId  # noqa: E402
from app.models.module import ApplicationModule  # noqa: E402
from app.models.role import Permission, Role, RolePermission  # noqa: E402
from app.models.user import User, UserModuleRole  # noqa: E402
from app.models.user_module_client_scope import UserModuleClientScope  # noqa: E402

# Legacy talent-api integer-id convention shared with
# apps/talent-api/scripts/seed.py — see module docstring. These are now
# resolved to a canonical platform Client.public_id via client_external_ids.
ABC_CLIENT_ID = 1
XYZ_CLIENT_ID = 2
NOVA_CLIENT_ID = 3

# (public_id, name, legacy talent-api id). platform-api owns canonical
# Client / Organisation identity (Architecture Completion Plan §6.1); the
# d4e5f6a7b8c9 migration seeds the same three rows.
_CANONICAL_CLIENTS = [
    ("cli-abc-company", "ABC Company", ABC_CLIENT_ID),
    ("cli-xyz-company", "XYZ Company", XYZ_CLIENT_ID),
    ("cli-nova-solutions", "Nova Solutions", NOVA_CLIENT_ID),
]
_LEGACY_TO_PUBLIC = {legacy: public_id for public_id, _n, legacy in _CANONICAL_CLIENTS}


def seed_canonical_clients(db) -> None:
    """Get-or-create the platform-owned canonical Client rows + the
    talent-api legacy-id crosswalk. Idempotent."""
    for public_id, name, legacy_id in _CANONICAL_CLIENTS:
        client = db.query(Client).filter_by(public_id=public_id).one_or_none()
        if client is None:
            client = Client(public_id=public_id, name=name, status="ACTIVE")
            db.add(client)
            db.flush()
        xref = (
            db.query(ClientExternalId)
            .filter_by(provider="talent-api", external_id=str(legacy_id))
            .one_or_none()
        )
        if xref is None:
            db.add(
                ClientExternalId(
                    client_id=client.id, provider="talent-api", external_id=str(legacy_id)
                )
            )
    db.commit()


def reset_schema() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def seed_authorization_catalog(db) -> None:
    """Populate the Role / Permission / RolePermission catalog from the
    single source of truth in ``app.core.permissions``. Mirrors the Alembic
    migration's backfill so a fresh ``--reset`` reseed and a migrated
    existing database end up identical.

    Idempotent/convergent: get-or-create by key rather than unconditional
    insert, so re-running after ``ALL_PERMISSIONS``/``ALL_ROLES`` gained new
    entries (e.g. the DijiBirthday role/permission catalog, added after this
    local DB was first seeded) picks up the new rows on the next run instead
    of raising a unique-constraint error or silently staying stale.
    """
    permission_ids: dict[str, int] = {}
    for perm in ALL_PERMISSIONS:
        row = db.query(Permission).filter_by(key=perm.key).one_or_none()
        if row is None:
            row = Permission(
                key=perm.key, name=perm.name, description=perm.description,
                module_key=perm.module_key, category=perm.category,
            )
            db.add(row)
            db.flush()
        permission_ids[perm.key] = row.id

    for role_def in ALL_ROLES:
        role = (
            db.query(Role)
            .filter_by(module_key=role_def.module_key, key=role_def.key)
            .one_or_none()
        )
        if role is None:
            role = Role(
                module_key=role_def.module_key, key=role_def.key, name=role_def.name,
                description=role_def.description, is_system=True,
            )
            db.add(role)
            db.flush()
        existing_perm_ids = {
            rp.permission_id
            for rp in db.query(RolePermission).filter_by(role_id=role.id).all()
        }
        for perm_key in role_def.permissions:
            perm_id = permission_ids[perm_key]
            if perm_id not in existing_perm_ids:
                db.add(RolePermission(role_id=role.id, permission_id=perm_id))
    db.commit()


def seed_module_registry(db) -> None:
    """Get-or-create + converge the ``ApplicationModule`` registry rows.

    Unlike the old ``db.add_all(...)`` this always runs and always brings
    each row's mutable fields (status/enabled/route/required_roles/
    display_order/name/description/icon) in line with the source-of-truth
    definitions below, even if the row already existed from an earlier
    seed run — e.g. flipping DijiBirthday from COMING_SOON to ACTIVE after
    Phase A-D shipped real functionality, without needing ``--reset``.
    """
    definitions = [
        dict(
            key=MODULE_TALENT_FLOW, name="DijiTalentFlow",
            description="Talent Operations and Client Tracking", icon="Users",
            route="/talent-flow", status="ACTIVE", enabled=True,
            display_order=1, required_roles="ANY",
        ),
        dict(
            key=MODULE_BIRTHDAY, name="DijiBirthday",
            description="Birthday Workflow Automation", icon="Cake",
            route="/birthday", status="ACTIVE", enabled=True,
            display_order=2,
            # Phase A-D shipped real functionality (birthday-api +
            # birthday-web) — same gating as DijiTalentFlow: only users
            # with an actual BIRTHDAY_* module assignment see the card.
            required_roles="ANY",
        ),
        dict(
            key=MODULE_SPARK, name="DijiSpark",
            description="HR / Spark Hire Workflows", icon="Sparkles",
            route="/spark", status="COMING_SOON", enabled=True,
            display_order=3, required_roles="",
        ),
    ]
    for fields in definitions:
        existing = db.query(ApplicationModule).filter_by(key=fields["key"]).one_or_none()
        if existing is None:
            db.add(ApplicationModule(**fields))
        else:
            for attr, value in fields.items():
                setattr(existing, attr, value)
    db.commit()


def _assign_client_scope(db, module_role: UserModuleRole, *, client_id: int | None) -> None:
    if client_id is not None:
        db.add(
            UserModuleClientScope(
                user_module_role_id=module_role.id,
                client_id=client_id,
                client_ref=_LEGACY_TO_PUBLIC.get(client_id),
                all_clients=False,
            )
        )
    else:
        db.add(UserModuleClientScope(user_module_role_id=module_role.id, all_clients=True))


def seed() -> None:
    db = SessionLocal()
    try:
        seed_authorization_catalog(db)

        # --- Canonical client identity (platform-owned, §6.1) ----------
        seed_canonical_clients(db)

        # --- Module registry --------------------------------------------
        seed_module_registry(db)

        # --- Users / dev personas -----------------------------------------
        # Get-or-create by email so a second run without --reset converges
        # rather than raising a unique-constraint error, and so module-role
        # assignments below can be added onto personas that already exist
        # in the local DB from an earlier seed run.
        persona_defs = [
            dict(
                email="madushanka@dijitalteam.com", full_name="Madushanka Weeriyasinghe",
                title="Talent Acquisition Specialist", platform_role=PlatformRole.PLATFORM_USER.value,
                persona_key="madushanka-ta", avatar_color="#c9431d",
            ),
            dict(
                email="tharindu.fernando@dijitalteam.com", full_name="Tharindu Fernando",
                title="Customer Success Lead", platform_role=PlatformRole.PLATFORM_USER.value,
                persona_key="customer-success", avatar_color="#db4d18",
            ),
            dict(
                email="sanduni.wickrama@dijitalteam.com", full_name="Sanduni Wickrama",
                title="TA Manager", platform_role=PlatformRole.PLATFORM_USER.value,
                persona_key="ta-manager", avatar_color="#aa2f1d",
            ),
            dict(
                email="admin@dijitalteam.com", full_name="Dilani Rathnayake",
                title="Platform Administrator", platform_role=PlatformRole.PLATFORM_ADMIN.value,
                persona_key="platform-admin", avatar_color="#8f2417",
            ),
            dict(
                email="superadmin@dijitalteam.com", full_name="Priyantha Bandara",
                title="DijiOne Super Admin", platform_role=PlatformRole.SUPER_ADMIN.value,
                persona_key="super-admin", avatar_color="#5c1a15",
            ),
            dict(
                email="amal.perera@abc-company.example", full_name="Amal Perera",
                title="Head of Talent, ABC Company", platform_role=PlatformRole.PLATFORM_USER.value,
                persona_key="abc-client", avatar_color="#f26a1b",
            ),
            dict(
                email="nadeesha.silva@xyz-company.example", full_name="Nadeesha Silva",
                title="VP Engineering, XYZ Company", platform_role=PlatformRole.PLATFORM_USER.value,
                persona_key="xyz-client", avatar_color="#f59e0b",
            ),
            dict(
                email="kasun.jayasuriya@nova-solutions.example", full_name="Kasun Jayasuriya",
                title="COO, Nova Solutions", platform_role=PlatformRole.PLATFORM_USER.value,
                persona_key="nova-client", avatar_color="#fbc34a",
            ),
            dict(
                email="ruwan.gunasekara@dijitalteam.com", full_name="Ruwan Gunasekara",
                title="Talent Acquisition Specialist (ABC + XYZ Portfolio)",
                platform_role=PlatformRole.PLATFORM_USER.value,
                persona_key="ta-portfolio", avatar_color="#f26a1b",
            ),
        ]
        users_by_persona: dict[str, User] = {}
        for fields in persona_defs:
            existing = db.query(User).filter_by(email=fields["email"]).one_or_none()
            if existing is None:
                existing = User(**fields)
                db.add(existing)
                db.flush()
            users_by_persona[fields["persona_key"]] = existing
        db.commit()

        madushanka = users_by_persona["madushanka-ta"]
        cs_user = users_by_persona["customer-success"]
        ta_manager = users_by_persona["ta-manager"]
        platform_admin = users_by_persona["platform-admin"]
        super_admin = users_by_persona["super-admin"]
        abc_client_user = users_by_persona["abc-client"]
        xyz_client_user = users_by_persona["xyz-client"]
        nova_client_user = users_by_persona["nova-client"]
        ta_portfolio_user = users_by_persona["ta-portfolio"]

        # Demonstrates DijiOne Phase 2 client/portfolio scope (CR §22): every
        # staff assignment defaults to ALL_CLIENTS except ta_portfolio_user,
        # who is explicitly restricted to ABC + XYZ (Nova excluded).
        module_roles = [
            (madushanka, MODULE_TALENT_FLOW, "TA_MEMBER", None, None),
            (cs_user, MODULE_TALENT_FLOW, "CUSTOMER_SUCCESS", None, None),
            (ta_manager, MODULE_TALENT_FLOW, "TA_MANAGER", None, None),
            (platform_admin, MODULE_TALENT_FLOW, "TA_MANAGER", None, None),
            (abc_client_user, MODULE_TALENT_FLOW, "TALENT_CLIENT", ABC_CLIENT_ID, None),
            (xyz_client_user, MODULE_TALENT_FLOW, "TALENT_CLIENT", XYZ_CLIENT_ID, None),
            (nova_client_user, MODULE_TALENT_FLOW, "TALENT_CLIENT", NOVA_CLIENT_ID, None),
            (ta_portfolio_user, MODULE_TALENT_FLOW, "TA_MEMBER", None, [ABC_CLIENT_ID, XYZ_CLIENT_ID]),
            # DijiBirthday (Phase A-D): grant the Super Admin dev persona
            # BIRTHDAY_ADMIN so the "Super Admin can't see DijiBirthday"
            # local-env bug has a persona to actually demo the fix with —
            # mirrors platform_admin's explicit TA_MANAGER grant above.
            # DijiOne's authorization model is module-aware by design (CLAUDE.md
            # §11): SUPER_ADMIN is a *platform* role and does not implicitly
            # carry business-module roles, so this must be explicit, same as
            # every other persona/module pairing in this table.
            (super_admin, MODULE_BIRTHDAY, "BIRTHDAY_ADMIN", None, None),
        ]
        for user, module_key, role, client_id, portfolio in module_roles:
            existing_role = (
                db.query(UserModuleRole)
                .filter_by(user_id=user.id, module_key=module_key, role=role)
                .one_or_none()
            )
            if existing_role is not None:
                continue
            module_role = UserModuleRole(
                user_id=user.id, module_key=module_key, role=role, client_id=client_id,
                client_ref=_LEGACY_TO_PUBLIC.get(client_id) if client_id is not None else None,
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
