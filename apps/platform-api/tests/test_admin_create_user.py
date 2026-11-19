"""D4: an administrator can add an internal employee before their first sign-in."""

import pytest

from app.core.config import get_settings
from app.models.audit_log import AuditLog
from app.models.user import User
from app.services.authorization_service import AuthorizationService
from app.services.entra_service import EntraIdentityConflictError, resolve_entra_user
from tests.conftest import auth_headers

TENANT = "tenant-1"
ISS = f"https://login.microsoftonline.com/{TENANT}/v2.0"
URL = "/api/platform/admin/users"
NEW = {"email": "New.Hire@Dijital.Example", "full_name": " New Hire "}


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setenv("ENTRA_TENANT_ID", TENANT)
    monkeypatch.setenv("ENTRA_INTERNAL_EMAIL_DOMAINS", "dijital.example")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def admin(api_client, two_tenant_world):
    return auth_headers(api_client, "test-platform-admin")


def test_added_user_is_active_unlinked_and_holds_no_access(api_client, db, admin, two_tenant_world):
    resp = api_client.post(URL, json=NEW, headers=admin)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert (body["email"], body["full_name"], body["platform_role"]) == ("new.hire@dijital.example", "New Hire", "PLATFORM_USER")
    assert body["is_active"] is True
    assert body["entra_object_id"] is None
    assert body["module_assignments"] == []

    user = db.get(User, body["id"])
    assert AuthorizationService(db).effective_module_roles(user) == {}
    assert AuthorizationService(db).platform_permissions(user) == frozenset()
    entry = db.query(AuditLog).filter_by(action="user.created", entity_id=user.id).one()
    assert entry.actor_id == two_tenant_world["platform_admin"].id


def test_added_user_can_be_granted_access_then_signs_in(api_client, db, admin):
    user_id = api_client.post(URL, json=NEW, headers=admin).json()["id"]
    assert api_client.put(
        f"{URL}/{user_id}/modules/talent-flow",
        json={"role": "TA_MEMBER", "enabled": True, "client_scope": {"all_clients": True, "client_ids": []}},
        headers=admin,
    ).status_code == 200

    claims = {"oid": "oid-new", "email": "new.hire@dijital.example", "name": "New Hire", "tid": TENANT, "iss": ISS, "acct": 0}
    signed_in = resolve_entra_user(db, claims)
    assert signed_in.id == user_id
    assert signed_in.entra_object_id == "oid-new"
    assert [g.role for g in AuthorizationService(db).effective_module_roles(signed_in)["talent-flow"]] == ["TA_MEMBER"]


def test_guest_identity_cannot_claim_an_added_user(api_client, db, admin):
    api_client.post(URL, json=NEW, headers=admin)
    guest = {"oid": "oid-guest", "email": "new.hire@dijital.example", "name": "G", "tid": TENANT, "iss": ISS, "acct": 1}
    with pytest.raises(EntraIdentityConflictError):
        resolve_entra_user(db, guest)


def test_duplicate_email_is_rejected_ignoring_case(api_client, db, admin):
    assert api_client.post(URL, json=NEW, headers=admin).status_code == 201
    resp = api_client.post(URL, json={"email": "NEW.HIRE@dijital.example", "full_name": "Again"}, headers=admin)
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]
    assert db.query(User).filter(User.email.ilike("new.hire@%")).count() == 1


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"email": "someone@gmail.com", "full_name": "Outsider"}, "Only internal email addresses"),
        ({"email": "not-an-email", "full_name": "X"}, "valid email"),
        ({"email": "a b@dijital.example", "full_name": "X"}, "valid email"),
        ({"email": "ok@dijital.example", "full_name": "   "}, "Full name is required"),
    ],
)
def test_invalid_input_is_rejected_with_a_clear_message(api_client, db, admin, payload, message):
    before = db.query(User).count()
    resp = api_client.post(URL, json=payload, headers=admin)
    assert resp.status_code == 400
    assert message in resp.json()["detail"]
    assert db.query(User).count() == before


def test_nobody_can_be_added_when_no_internal_domain_is_configured(api_client, admin, monkeypatch):
    monkeypatch.setenv("ENTRA_INTERNAL_EMAIL_DOMAINS", "")
    get_settings.cache_clear()
    resp = api_client.post(URL, json=NEW, headers=admin)
    assert resp.status_code == 400
    assert "no internal email domain" in resp.json()["detail"]


def test_adding_a_user_needs_manage_users(api_client, db, two_tenant_world):
    resp = api_client.post(URL, json=NEW, headers=auth_headers(api_client, "test-ta"))
    assert resp.status_code == 403
    assert api_client.post(URL, json=NEW).status_code == 401
