"""An Entra identity may never inherit another identity's DijiOne account."""

import pytest

from app.core.config import get_settings
from app.models.user import User, UserModuleRole
from app.services.claims_service import build_claims
from app.services.entra_service import EntraIdentityConflictError, EntraLoginRefusedError, resolve_entra_user

TENANT = "tenant-1"
EMAIL = "person@dijital.example"


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setenv("ENTRA_TENANT_ID", TENANT)
    monkeypatch.setenv("ENTRA_INTERNAL_EMAIL_DOMAINS", "dijital.example")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def member(oid="oid-1", email=EMAIL, **over):
    return {"oid": oid, "email": email, "name": "P", "tid": TENANT, "acct": 0, **over}


def account(db, oid=None, email=EMAIL):
    user = User(email=email, full_name="P", is_active=True, entra_object_id=oid)
    db.add(user)
    db.flush()
    db.add(UserModuleRole(user_id=user.id, module_key="talent-flow", role="TA_MANAGER"))
    db.commit()
    return user


def assert_untouched(db, user, oid):
    db.rollback()
    db.expire_all()
    assert db.get(User, user.id).entra_object_id == oid
    assert db.query(User).filter_by(email=EMAIL).count() == 1


def test_existing_linked_user_signs_in_by_object_id(db):
    user = account(db, oid="oid-1")
    assert resolve_entra_user(db, member()).id == user.id


def test_linked_user_keeps_account_when_email_claim_changes(db):
    user = account(db, oid="oid-1")
    assert resolve_entra_user(db, member(email="renamed@dijital.example")).id == user.id


def test_proven_member_links_a_preprovisioned_account_once(db):
    user = account(db)
    assert resolve_entra_user(db, member()).entra_object_id == "oid-1"
    assert resolve_entra_user(db, member()).id == user.id


def test_collision_with_an_account_linked_elsewhere_is_refused(db):
    user = account(db, oid="oid-owner")
    with pytest.raises(EntraIdentityConflictError):
        resolve_entra_user(db, member(oid="oid-other"))
    assert_untouched(db, user, "oid-owner")


@pytest.mark.parametrize(
    "over",
    [
        {"acct": 1},
        {"acct": None},
        {"tid": "other"},
        {"idp": "live.com"},
        {"preferred_username": "person_x.com#EXT#@t.example"},
    ],
)
def test_guest_or_unproven_identity_cannot_claim_an_account(db, over):
    user = account(db)
    with pytest.raises(EntraIdentityConflictError):
        resolve_entra_user(db, member(oid="oid-guest", **over))
    assert_untouched(db, user, None)


def test_refused_identity_receives_no_permissions(db):
    user = account(db)
    assert "talent-flow" in build_claims(user, db)["module_roles"]
    with pytest.raises(EntraIdentityConflictError):
        resolve_entra_user(db, member(oid="oid-guest", acct=1))
    assert db.query(User).filter_by(entra_object_id="oid-guest").count() == 0


def test_conflict_is_refused_as_a_login_failure_with_a_generic_message(db):
    account(db, oid="oid-owner")
    with pytest.raises(EntraLoginRefusedError) as raised:
        resolve_entra_user(db, member(oid="oid-other"))
    assert EMAIL not in str(raised.value)


def test_new_member_is_created_inactive_and_refused_until_activated(db):
    with pytest.raises(EntraLoginRefusedError):
        resolve_entra_user(db, member(oid="oid-new", email="new@dijital.example"))
    user = db.query(User).filter_by(entra_object_id="oid-new").one()
    assert not user.is_active and user.internal_employee


def test_new_guest_is_created_inactive_and_never_internal(db):
    with pytest.raises(EntraLoginRefusedError):
        resolve_entra_user(db, member(oid="oid-g", email="g@other.example", acct=1))
    user = db.query(User).filter_by(entra_object_id="oid-g").one()
    assert not user.is_active and not user.internal_employee
