"""Email Safety (BirthdayTestEmailRecipient) admin surface — CRUD, RBAC,
non-production-only enforcement, and audit trail. See
docs/platform/email-architecture.md.

Mail-policy integration (the allowlist actually gating outbound Graph
sends) is covered separately in tests/test_mail_policy_integration.py.
"""

from __future__ import annotations

from tests.conftest import headers_for, supplier_headers_for


def _create_recipient(api_client, headers, email="test.person@dijitalteam.com", **overrides):
    payload = {
        "email_address": email,
        "display_label": overrides.pop("display_label", "Test Person"),
        "recipient_type": overrides.pop("recipient_type", "INTERNAL_TESTER"),
        **overrides,
    }
    resp = api_client.post("/api/birthday/admin/test-email-recipients", json=payload, headers=headers)
    return resp


def test_create_and_list_recipient(api_client, db):
    admin = headers_for(400, role="BIRTHDAY_ADMIN")
    resp = _create_recipient(api_client, admin)
    assert resp.status_code == 201
    body = resp.json()
    assert body["email_address"] == "test.person@dijitalteam.com"
    assert body["display_label"] == "Test Person"
    assert body["recipient_type"] == "INTERNAL_TESTER"
    assert body["is_active"] is True
    assert body["created_by"] == 400

    listed = api_client.get("/api/birthday/admin/test-email-recipients", headers=admin)
    assert listed.status_code == 200
    assert any(r["email_address"] == "test.person@dijitalteam.com" for r in listed.json()["items"])


def test_duplicate_recipient_rejected_case_insensitively(api_client, db):
    admin = headers_for(401, role="BIRTHDAY_ADMIN")
    first = _create_recipient(api_client, admin, email="Dup.Person@DijitalTeam.com")
    assert first.status_code == 201

    dup = _create_recipient(api_client, admin, email="dup.person@dijitalteam.com")
    assert dup.status_code == 409


def test_invalid_email_syntax_rejected(api_client, db):
    admin = headers_for(402, role="BIRTHDAY_ADMIN")
    resp = _create_recipient(api_client, admin, email="not-an-email")
    assert resp.status_code == 422


def test_wildcard_recipient_rejected(api_client, db):
    admin = headers_for(403, role="BIRTHDAY_ADMIN")
    resp = _create_recipient(api_client, admin, email="*@dijitalteam.com")
    assert resp.status_code == 422


def test_update_label_and_type(api_client, db):
    admin = headers_for(404, role="BIRTHDAY_ADMIN")
    created = _create_recipient(api_client, admin).json()

    resp = api_client.patch(
        f"/api/birthday/admin/test-email-recipients/{created['id']}",
        json={"display_label": "Updated Label", "recipient_type": "TEST_SUPPLIER"},
        headers=admin,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["display_label"] == "Updated Label"
    assert body["recipient_type"] == "TEST_SUPPLIER"
    # The address itself is never editable via PATCH.
    assert body["email_address"] == "test.person@dijitalteam.com"


def test_deactivate_and_reactivate_recipient(api_client, db):
    admin = headers_for(405, role="BIRTHDAY_ADMIN")
    created = _create_recipient(api_client, admin).json()

    deactivated = api_client.patch(
        f"/api/birthday/admin/test-email-recipients/{created['id']}",
        json={"is_active": False},
        headers=admin,
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    reactivated = api_client.patch(
        f"/api/birthday/admin/test-email-recipients/{created['id']}",
        json={"is_active": True},
        headers=admin,
    )
    assert reactivated.status_code == 200
    assert reactivated.json()["is_active"] is True


def test_inactive_recipient_excluded_from_eligible_sending(api_client, db):
    from app.services.test_email_recipient_service import list_active_recipient_emails

    admin = headers_for(406, role="BIRTHDAY_ADMIN")
    created = _create_recipient(api_client, admin, email="inactive.check@dijitalteam.com").json()
    assert created["normalized_email_address" if "normalized_email_address" in created else "email_address"]

    db.commit()
    assert "inactive.check@dijitalteam.com" in list_active_recipient_emails(db)

    api_client.patch(
        f"/api/birthday/admin/test-email-recipients/{created['id']}",
        json={"is_active": False},
        headers=admin,
    )
    db.commit()
    assert "inactive.check@dijitalteam.com" not in list_active_recipient_emails(db)


def test_delete_recipient(api_client, db):
    admin = headers_for(407, role="BIRTHDAY_ADMIN")
    created = _create_recipient(api_client, admin, email="delete.me@dijitalteam.com").json()

    resp = api_client.delete(f"/api/birthday/admin/test-email-recipients/{created['id']}", headers=admin)
    assert resp.status_code == 204

    listed = api_client.get("/api/birthday/admin/test-email-recipients", headers=admin).json()
    assert all(r["id"] != created["id"] for r in listed["items"])


def test_supplier_user_denied(api_client, db):
    from app.models.supplier import Supplier

    supplier = Supplier(name="Test Supplier Co", primary_contact_email="c@example.com", lead_time_days=2)
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    supplier_hdrs = supplier_headers_for(db, supplier)

    resp = api_client.get("/api/birthday/admin/test-email-recipients", headers=supplier_hdrs)
    assert resp.status_code == 403


def test_non_admin_internal_user_denied(api_client, db):
    user_hdrs = headers_for(408, role="BIRTHDAY_USER")
    resp = api_client.get("/api/birthday/admin/test-email-recipients", headers=user_hdrs)
    assert resp.status_code == 403


def test_unauthenticated_denied(api_client, db):
    resp = api_client.get("/api/birthday/admin/test-email-recipients")
    assert resp.status_code == 401


def test_prod_route_unavailable(api_client, db, monkeypatch):
    """Backend enforcement is independent of the frontend nav — in a
    production-configured deployment, require_non_production() 404s the
    entire Email Safety admin surface regardless of role."""
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("APP_ENV", "prod")
    get_settings.cache_clear()
    try:
        admin = headers_for(409, role="BIRTHDAY_ADMIN")
        resp = api_client.get("/api/birthday/admin/test-email-recipients", headers=admin)
        assert resp.status_code == 404
    finally:
        monkeypatch.delenv("APP_ENV", raising=False)
        get_settings.cache_clear()


def test_audit_events_recorded_for_create_update_deactivate(api_client, db, platform_calls):
    admin = headers_for(410, role="BIRTHDAY_ADMIN")
    created = _create_recipient(api_client, admin, email="audit.check@dijitalteam.com").json()

    actions = [c["action"] for c in platform_calls["audit_events"]]
    assert "TEST_EMAIL_RECIPIENT_CREATED" in actions

    api_client.patch(
        f"/api/birthday/admin/test-email-recipients/{created['id']}",
        json={"is_active": False},
        headers=admin,
    )
    actions = [c["action"] for c in platform_calls["audit_events"]]
    assert "TEST_EMAIL_RECIPIENT_DEACTIVATED" in actions

    api_client.patch(
        f"/api/birthday/admin/test-email-recipients/{created['id']}",
        json={"display_label": "Renamed"},
        headers=admin,
    )
    actions = [c["action"] for c in platform_calls["audit_events"]]
    assert "TEST_EMAIL_RECIPIENT_UPDATED" in actions
