"""Regression coverage for scripts/seed.py's idempotent convergence
behavior (added alongside the fix for the local-env bug where DijiBirthday
stayed COMING_SOON and the Super Admin dev persona had no DijiBirthday
access, because the old seed() only ever inserted rows and errored/no-opped
on a second run instead of converging an already-seeded DB).
"""

import importlib.util
from pathlib import Path

from app.core.constants import MODULE_BIRTHDAY, MODULE_TALENT_FLOW
from app.models.module import ApplicationModule
from app.models.user import User, UserModuleRole

_SEED_PATH = Path(__file__).resolve().parents[1] / "scripts" / "seed.py"
_spec = importlib.util.spec_from_file_location("dijione_seed_script", _SEED_PATH)
seed_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_module)


def test_seed_converges_stale_module_status_to_active(db):
    """Re-running the module-registry convergence step must flip an
    existing COMING_SOON row to ACTIVE (not just insert-if-missing) —
    this is the root cause of DijiOne Home showing DijiBirthday as
    "COMING SOON" after the source definition had already moved on."""
    db.add(
        ApplicationModule(
            key=MODULE_BIRTHDAY, name="DijiBirthday", description="stale",
            icon="Cake", route="/birthday", status="COMING_SOON", enabled=True,
            display_order=2, required_roles="",
        )
    )
    db.commit()

    seed_module.seed_module_registry(db)
    db.expire_all()

    row = db.query(ApplicationModule).filter_by(key=MODULE_BIRTHDAY).one()
    assert row.status == "ACTIVE"
    assert row.required_roles == "ANY"


def test_seed_grants_super_admin_birthday_admin_role(db):
    """After a full seed() run, the seeded Super Admin persona must resolve
    a birthday:BIRTHDAY_ADMIN module role — SUPER_ADMIN does not implicitly
    inherit business-module access in this codebase (see
    AuthorizationService.effective_module_roles, which only reads DIRECT
    UserModuleRole / GroupModuleRole grants), so this has to be an explicit
    seeded assignment, mirroring how every other module-role pairing in
    seed.py is explicit."""
    from app.db.session import SessionLocal

    seed_module.seed()

    session = SessionLocal()
    try:
        super_admin = session.query(User).filter_by(persona_key="super-admin").one()
        birthday_role = (
            session.query(UserModuleRole)
            .filter_by(user_id=super_admin.id, module_key=MODULE_BIRTHDAY)
            .one_or_none()
        )
        assert birthday_role is not None
        assert birthday_role.role == "BIRTHDAY_ADMIN"
        assert birthday_role.enabled is True

        # Regression guard: a TalentFlow-only client persona must NOT pick
        # up birthday access as a side effect of this change.
        real_client = session.query(User).filter_by(persona_key="cms-group-client").one()
        real_client_birthday_role = (
            session.query(UserModuleRole)
            .filter_by(user_id=real_client.id, module_key=MODULE_BIRTHDAY)
            .one_or_none()
        )
        assert real_client_birthday_role is None

        # And the pre-existing talent-flow role assignment must be intact.
        real_client_talent_role = (
            session.query(UserModuleRole)
            .filter_by(user_id=real_client.id, module_key=MODULE_TALENT_FLOW)
            .one_or_none()
        )
        assert real_client_talent_role is not None
        assert real_client_talent_role.role == "TALENT_CLIENT"
    finally:
        session.close()


def test_seed_is_idempotent_on_rerun(db):
    """Running seed() twice must not raise and must not duplicate rows —
    this is exactly the scenario that broke local dev: editing seed.py's
    source and expecting a rerun (without --reset) to converge the DB."""
    from app.db.session import SessionLocal

    seed_module.seed()
    seed_module.seed()  # must not raise a unique-constraint error

    session = SessionLocal()
    try:
        module_count = session.query(ApplicationModule).count()
        assert module_count == 3  # talent-flow, birthday, spark — no duplicates

        birthday_role_count = (
            session.query(UserModuleRole).filter_by(module_key=MODULE_BIRTHDAY).count()
        )
        assert birthday_role_count == 1
    finally:
        session.close()
