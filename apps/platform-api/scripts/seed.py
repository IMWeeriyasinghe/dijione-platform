"""Seeds Platform Core's local demo data: the Role/Permission catalog, the
module registry, dev personas, module-role assignments, client/portfolio
scope, and the canonical Client/Organisation identity.

Run with:  python scripts/seed.py [--reset]

Coordinated seeding across services: platform-api is the permanent owner of
canonical Client identity (Architecture Completion Plan §6.1) —
``seed_canonical_clients`` creates the real, DTC-verified ``Client`` rows
here (``app.core.real_dev_clients.REAL_DEV_CLIENTS`` — see that module's
docstring for the discovery record; imported by both this script and the
``h8i9j0k1l2m3`` migration so the two never drift), replacing the old
ABC/XYZ/Nova demo set (DijiTalentFlow real-data local validation,
2026-09-01). Every ``UserModuleClientScope`` / ``UserModuleRole`` row below
keys on the real ``client_ref`` (a ``Client.public_id``) directly — there is
no legacy bare-integer convention to preserve now that
``apps/talent-api``'s own seed script also creates its ``Client`` extension
rows from this same real list rather than a fixed creation order. Run this
script *before* talent-api's, since talent-api's seed fetches the real
client directory from platform-api's running API
(``GET /api/platform/internal/clients``). See docs/platform/
local-development.md and docs/platform/data-ownership.md §1.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.constants import MODULE_BIRTHDAY, MODULE_SPARK, MODULE_TALENT_FLOW, PlatformRole  # noqa: E402
from app.core.permissions import ALL_PERMISSIONS, ALL_ROLES  # noqa: E402
from app.core.real_dev_clients import PERSONA_CLIENTS, REAL_DEV_CLIENTS  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.module import ApplicationModule  # noqa: E402
from app.models.role import Permission, Role, RolePermission  # noqa: E402
from app.models.user import User, UserModuleRole  # noqa: E402
from app.models.user_module_client_scope import UserModuleClientScope  # noqa: E402


def seed_canonical_clients(db) -> None:
    """Get-or-create the platform-owned canonical Client rows for the real,
    DTC-verified client set. Idempotent."""
    for real_client in REAL_DEV_CLIENTS:
        client = db.query(Client).filter_by(public_id=real_client.public_id).one_or_none()
        if client is None:
            db.add(Client(public_id=real_client.public_id, name=real_client.name, status="ACTIVE"))
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


def _assign_client_scope(db, module_role: UserModuleRole, *, client_ref: str | None) -> None:
    if client_ref is not None:
        db.add(
            UserModuleClientScope(
                user_module_role_id=module_role.id, client_ref=client_ref, all_clients=False,
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
            # Real, DTC-verified persona clients (PERSONA_CLIENTS — the
            # subset of REAL_DEV_CLIENTS with the most real posting volume
            # in the live discovery run; see real_dev_clients.py docstring).
            # These local dev logins represent the real client
            # organisation for demo purposes only — no specific real
            # employee is asserted, so the persona's full_name is a
            # generic role label, not an invented person's name.
            dict(
                email="client@cms-group.example", full_name="CMS group Client Contact",
                title="Client Contact, CMS group", platform_role=PlatformRole.PLATFORM_USER.value,
                persona_key="cms-group-client", avatar_color="#f26a1b",
            ),
            dict(
                email="client@databl-io.example", full_name="Databl.io Client Contact",
                title="Client Contact, Databl.io", platform_role=PlatformRole.PLATFORM_USER.value,
                persona_key="databl-io-client", avatar_color="#f59e0b",
            ),
            dict(
                email="client@portal-technology.example", full_name="Portal Technology Client Contact",
                title="Client Contact, Portal Technology", platform_role=PlatformRole.PLATFORM_USER.value,
                persona_key="portal-technology-client", avatar_color="#fbc34a",
            ),
            dict(
                email="ruwan.gunasekara@dijitalteam.com", full_name="Ruwan Gunasekara",
                title="Talent Acquisition Specialist (Portfolio)",
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
        cms_group_client_user = users_by_persona["cms-group-client"]
        databl_io_client_user = users_by_persona["databl-io-client"]
        portal_technology_client_user = users_by_persona["portal-technology-client"]
        ta_portfolio_user = users_by_persona["ta-portfolio"]

        persona_client_refs = {c.name: c.public_id for c in PERSONA_CLIENTS}
        cms_group_ref = persona_client_refs["CMS group"]
        databl_io_ref = persona_client_refs["Databl.io"]
        portal_technology_ref = persona_client_refs["Portal Technology"]

        # Demonstrates DijiOne Phase 2 client/portfolio scope (CR §22): every
        # staff assignment defaults to ALL_CLIENTS except ta_portfolio_user,
        # who is explicitly restricted to a 2-client portfolio (CMS group +
        # Databl.io — Portal Technology excluded, same 2-of-3 shape as the
        # old ABC+XYZ/Nova-excluded portfolio it replaces).
        module_roles = [
            (madushanka, MODULE_TALENT_FLOW, "TA_MEMBER", None, None),
            (cs_user, MODULE_TALENT_FLOW, "CUSTOMER_SUCCESS", None, None),
            (ta_manager, MODULE_TALENT_FLOW, "TA_MANAGER", None, None),
            (platform_admin, MODULE_TALENT_FLOW, "TA_MANAGER", None, None),
            (cms_group_client_user, MODULE_TALENT_FLOW, "TALENT_CLIENT", cms_group_ref, None),
            (databl_io_client_user, MODULE_TALENT_FLOW, "TALENT_CLIENT", databl_io_ref, None),
            (portal_technology_client_user, MODULE_TALENT_FLOW, "TALENT_CLIENT", portal_technology_ref, None),
            (ta_portfolio_user, MODULE_TALENT_FLOW, "TA_MEMBER", None, [cms_group_ref, databl_io_ref]),
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
        for user, module_key, role, client_ref, portfolio in module_roles:
            existing_role = (
                db.query(UserModuleRole)
                .filter_by(user_id=user.id, module_key=module_key, role=role)
                .one_or_none()
            )
            if existing_role is not None:
                continue
            module_role = UserModuleRole(
                user_id=user.id, module_key=module_key, role=role, client_ref=client_ref,
            )
            db.add(module_role)
            db.flush()
            if portfolio is not None:
                for portfolio_client_ref in portfolio:
                    _assign_client_scope(db, module_role, client_ref=portfolio_client_ref)
            else:
                _assign_client_scope(db, module_role, client_ref=client_ref)
        db.commit()

        print("Platform Core seed complete.")
        print(
            "  Dev personas: madushanka-ta, customer-success, ta-manager, "
            "platform-admin, super-admin, cms-group-client, databl-io-client, "
            "portal-technology-client, ta-portfolio (CMS group + Databl.io only)"
        )
        print("  Now run: (cd ../talent-api && python scripts/seed.py [--reset])")
    finally:
        db.close()


if __name__ == "__main__":
    if "--reset" in sys.argv:
        reset_schema()
    seed()
