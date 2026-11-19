"""A protected administrator's SUPER_ADMIN privilege cannot be removed through DijiOne, even by
another SUPER_ADMIN, while every other account stays manageable."""

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.models.audit_log import AuditLog
from app.models.protected_admin import ProtectedAdmin
from app.models.role import Permission, Role, RolePermission
from app.models.user import User
from app.services.authorization_service import AuthorizationService
from app.services.entra_service import resolve_entra_user
from app.services.protected_admin import ProtectedAdminError
from tests.conftest import auth_headers

EMAIL = "protected.admin@example.com"
ISS = "https://login.microsoftonline.com/tenant-1/v2.0"
URL = "/api/platform/admin/users"


@pytest.fixture()
def protected(db, two_tenant_world):
    user = User(email=EMAIL, full_name="Protected Admin", platform_role="SUPER_ADMIN", persona_key="test-protected")
    db.add(user)
    db.commit()
    db.execute(
        text(
            "INSERT INTO protected_admins (email, required_role, created_at, updated_at) "
            "VALUES (:e, 'SUPER_ADMIN', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
        {"e": EMAIL},
    )
    db.commit()
    return user


@pytest.fixture()
def other_super(api_client, protected):
    return auth_headers(api_client, "test-super-admin")


def test_another_super_admin_cannot_demote_or_replace_the_role(api_client, db, protected, other_super):
    for role in ("PLATFORM_ADMIN", "PLATFORM_USER"):
        resp = api_client.patch(f"{URL}/{protected.id}/platform-role", json={"platform_role": role}, headers=other_super)
        assert resp.status_code == 403, resp.text
        assert "protected" in resp.json()["detail"].lower()
    db.expire_all()
    assert db.get(User, protected.id).platform_role == "SUPER_ADMIN"


def test_another_super_admin_cannot_deactivate_it(api_client, db, protected, other_super):
    resp = api_client.patch(f"{URL}/{protected.id}/status", json={"is_active": False}, headers=other_super)
    assert resp.status_code == 403, resp.text
    db.expire_all()
    assert db.get(User, protected.id).is_active is True


def test_blocked_attempts_are_audited(api_client, db, protected, other_super):
    api_client.patch(f"{URL}/{protected.id}/platform-role", json={"platform_role": "PLATFORM_USER"}, headers=other_super)
    entry = db.query(AuditLog).filter_by(action="protected_admin.change_blocked", entity_id=protected.id).one()
    assert "PLATFORM_USER" in entry.new_state


def test_setting_the_same_role_is_not_a_change(api_client, protected, other_super):
    body = {"platform_role": "SUPER_ADMIN"}
    resp = api_client.patch(f"{URL}/{protected.id}/platform-role", json=body, headers=other_super)
    assert resp.status_code == 200, resp.text
    assert resp.json()["protected"] is True


def test_the_user_is_shown_as_protected_and_others_are_not(api_client, protected, other_super, two_tenant_world):
    assert api_client.get(f"{URL}/{protected.id}", headers=other_super).json()["protected"] is True
    other = two_tenant_world["abc_user"]
    assert api_client.get(f"{URL}/{other.id}", headers=other_super).json()["protected"] is False


def test_other_accounts_and_other_super_admins_remain_manageable(api_client, db, protected, other_super, two_tenant_world):
    other = two_tenant_world["abc_user"]
    promote = {"platform_role": "PLATFORM_ADMIN"}
    assert api_client.patch(f"{URL}/{other.id}/platform-role", json=promote, headers=other_super).status_code == 200
    assert api_client.patch(f"{URL}/{other.id}/status", json={"is_active": False}, headers=other_super).status_code == 200
    # The other Super Admin is not protected: with the protected account present it can be demoted.
    sa = two_tenant_world["super_admin"]
    by_protected = auth_headers(api_client, "test-protected")
    assert api_client.patch(f"{URL}/{sa.id}/platform-role", json=promote, headers=by_protected).status_code == 200


def test_application_access_of_the_protected_user_stays_manageable(api_client, db, protected, other_super):
    resp = api_client.put(
        f"{URL}/{protected.id}/modules/talent-flow",
        json={"role": "TA_MEMBER", "enabled": True, "client_scope": {"all_clients": True, "client_ids": []}},
        headers=other_super,
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.parametrize(
    "change",
    [
        lambda u: setattr(u, "platform_role", "PLATFORM_USER"),
        lambda u: setattr(u, "is_active", False),
        lambda u: setattr(u, "email", "someone.else@example.com"),
    ],
)
def test_the_guard_refuses_any_orm_change_whatever_the_endpoint(db, protected, change):
    change(protected)
    with pytest.raises(ProtectedAdminError):
        db.commit()
    db.rollback()


def test_the_account_cannot_be_deleted_or_rebound(db, protected):
    db.delete(protected)
    with pytest.raises(ProtectedAdminError):
        db.commit()
    db.rollback()
    protected.entra_object_id = "oid-1"
    db.commit()  # first binding is allowed
    protected.entra_object_id = "oid-2"
    with pytest.raises(ProtectedAdminError):
        db.commit()
    db.rollback()


def test_the_policy_and_the_role_itself_cannot_be_altered(db, protected):
    db.add(ProtectedAdmin(email="x@example.com", required_role="SUPER_ADMIN"))
    with pytest.raises(ProtectedAdminError):
        db.commit()
    db.rollback()

    role = db.query(Role).filter_by(key="SUPER_ADMIN", module_key=None).one()
    db.delete(role)
    with pytest.raises(ProtectedAdminError):
        db.commit()
    db.rollback()

    link = db.query(RolePermission).join(Permission, Permission.id == RolePermission.permission_id).filter(
        RolePermission.role_id == role.id, Permission.key == "platform.admin.view_as"
    ).one()
    db.delete(link)
    with pytest.raises(ProtectedAdminError):
        db.commit()
    db.rollback()


def test_the_protected_user_holds_view_as(db, protected):
    assert "platform.admin.view_as" in AuthorizationService(db).platform_permissions(protected)


def test_sign_in_restores_the_required_state_and_records_the_identity(db, protected, monkeypatch):
    # The account was demoted by direct database access (the infrastructure recovery path).
    db.execute(text("UPDATE users SET platform_role = 'PLATFORM_USER' WHERE id = :i"), {"i": protected.id})
    db.commit()
    monkeypatch.setenv("ENTRA_TENANT_ID", "tenant-1")
    monkeypatch.setenv("ENTRA_INTERNAL_EMAIL_DOMAINS", "example.com")
    get_settings.cache_clear()
    try:
        user = resolve_entra_user(db, {"oid": "oid-p", "email": EMAIL, "name": "P", "tid": "tenant-1", "iss": ISS, "acct": 0})
    finally:
        get_settings.cache_clear()
    assert user.platform_role == "SUPER_ADMIN" and user.is_active is True
    assert db.execute(text("SELECT entra_object_id FROM protected_admins")).scalar_one() == "oid-p"
