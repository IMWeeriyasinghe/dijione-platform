"""Supplier Portal invitation workflow — automatic (on create) and manual
(Send/Resend Invite) sends, eligibility gating, idempotency (never a
second SupplierUser/guest), audit, and authorization."""

from __future__ import annotations

from tests.conftest import headers_for


def _admin():
    return headers_for(970, role="BIRTHDAY_ADMIN")


def _supplier(api_client, admin, **extra):
    body = {"name": "Invite Bakery", "primary_contact_email": "invite@bakery.example.com"}
    body.update(extra)
    return api_client.post("/api/birthday/suppliers", json=body, headers=admin).json()


# --- auto-invite on create -----------------------------------------------

def test_create_with_auto_invite_on_by_default_sends_and_stamps_invited_at(api_client, db):
    admin = _admin()
    sup = _supplier(api_client, admin)
    resp = api_client.post(
        f"/api/birthday/suppliers/{sup['id']}/users",
        json={"email": "baker@invite.example.com", "full_name": "Baker"},
        headers=admin,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["invited_at"] is not None
    assert body["invite_count"] == 1
    assert body["onboarding_state"] == "INVITED"
    assert body["invitation_detail"] == "Invitation sent to baker@invite.example.com."


def test_create_with_send_invitation_false_does_not_send(api_client, db):
    admin = _admin()
    sup = _supplier(api_client, admin)
    resp = api_client.post(
        f"/api/birthday/suppliers/{sup['id']}/users",
        json={"email": "nosend@invite.example.com", "send_invitation": False},
        headers=admin,
    )
    body = resp.json()
    assert body["invited_at"] is None
    assert body["invite_count"] == 0
    assert body["onboarding_state"] == "NOT_INVITED"
    assert body["invitation_detail"] is None


def test_create_records_an_audit_event_for_the_automatic_send(api_client, db, platform_calls):
    admin = _admin()
    sup = _supplier(api_client, admin)
    api_client.post(
        f"/api/birthday/suppliers/{sup['id']}/users",
        json={"email": "audited@invite.example.com"}, headers=admin,
    )
    sent_events = [
        e for e in platform_calls["audit_events"]
        if e.get("action") == "birthday.supplier_user.invite_sent"
    ]
    assert len(sent_events) == 1
    assert sent_events[0]["entity_type"] == "supplier_user"
    assert sent_events[0]["metadata"]["automatic"] is True
    assert sent_events[0]["metadata"]["recipient"] == "audited@invite.example.com"


# --- manual send / resend -------------------------------------------------

def test_manual_send_invite(api_client, db):
    admin = _admin()
    sup = _supplier(api_client, admin)
    user = api_client.post(
        f"/api/birthday/suppliers/{sup['id']}/users",
        json={"email": "manual@invite.example.com", "send_invitation": False},
        headers=admin,
    ).json()

    resp = api_client.post(
        f"/api/birthday/suppliers/{sup['id']}/users/{user['id']}/invite", headers=admin,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"sent": True, "detail": "Invitation sent to manual@invite.example.com."}


def test_resend_invite_increments_count_and_is_a_distinct_audit_event(api_client, db, platform_calls):
    admin = _admin()
    sup = _supplier(api_client, admin)
    user = api_client.post(
        f"/api/birthday/suppliers/{sup['id']}/users",
        json={"email": "resend@invite.example.com"}, headers=admin,  # auto-invite #1
    ).json()
    assert user["invite_count"] == 1

    api_client.post(f"/api/birthday/suppliers/{sup['id']}/users/{user['id']}/invite", headers=admin)  # #2
    api_client.post(f"/api/birthday/suppliers/{sup['id']}/users/{user['id']}/invite", headers=admin)  # #3

    listed = api_client.get(f"/api/birthday/suppliers/{sup['id']}/users", headers=admin).json()[0]
    assert listed["invite_count"] == 3

    sent_events = [
        e for e in platform_calls["audit_events"]
        if e.get("action") == "birthday.supplier_user.invite_sent"
    ]
    assert len(sent_events) == 3
    # exactly one row throughout — resend never creates a second user
    assert len(api_client.get(f"/api/birthday/suppliers/{sup['id']}/users", headers=admin).json()) == 1


def test_resend_never_creates_a_second_entra_link_or_user_row(api_client, db):
    """The invite endpoint never touches entra_object_id — it only ever
    sends mail and updates invite bookkeeping on the existing row."""
    admin = _admin()
    sup = _supplier(api_client, admin)
    user = api_client.post(
        f"/api/birthday/suppliers/{sup['id']}/users",
        json={"email": "linked@invite.example.com", "send_invitation": False}, headers=admin,
    ).json()
    api_client.patch(
        f"/api/birthday/suppliers/{sup['id']}/users/{user['id']}",
        json={"entra_object_id": "oid-invite-stable"}, headers=admin,
    )

    api_client.post(f"/api/birthday/suppliers/{sup['id']}/users/{user['id']}/invite", headers=admin)
    api_client.post(f"/api/birthday/suppliers/{sup['id']}/users/{user['id']}/invite", headers=admin)

    got = api_client.get(f"/api/birthday/suppliers/{sup['id']}/users", headers=admin).json()
    assert len(got) == 1
    assert got[0]["entra_object_id"] == "oid-invite-stable"


# --- eligibility gating ----------------------------------------------------

def test_deactivated_user_cannot_receive_invite(api_client, db):
    admin = _admin()
    sup = _supplier(api_client, admin)
    user = api_client.post(
        f"/api/birthday/suppliers/{sup['id']}/users",
        json={"email": "off@invite.example.com", "send_invitation": False}, headers=admin,
    ).json()
    api_client.patch(
        f"/api/birthday/suppliers/{sup['id']}/users/{user['id']}",
        json={"status": "INACTIVE"}, headers=admin,
    )

    resp = api_client.post(
        f"/api/birthday/suppliers/{sup['id']}/users/{user['id']}/invite", headers=admin,
    )
    assert resp.status_code == 409
    assert "deactivated" in resp.json()["detail"].lower()


def test_create_with_inactive_status_does_not_auto_invite(api_client, db):
    admin = _admin()
    sup = _supplier(api_client, admin)
    body = api_client.post(
        f"/api/birthday/suppliers/{sup['id']}/users",
        json={"email": "createdoff@invite.example.com", "status": "INACTIVE"}, headers=admin,
    ).json()
    assert body["invitation_detail"] is None
    assert body["invited_at"] is None


def test_invite_unknown_user_404(api_client, db):
    admin = _admin()
    sup = _supplier(api_client, admin)
    resp = api_client.post(
        f"/api/birthday/suppliers/{sup['id']}/users/999999/invite", headers=admin,
    )
    assert resp.status_code == 404


# --- transport failure handling --------------------------------------------

def test_email_failure_is_reported_honestly_not_as_success(api_client, db, monkeypatch):
    from mail_client_py import MailOutcome, MailResult

    class _AlwaysFails:
        def send(self, *, to, subject, body, correlation_id=None, content_type="Text"):
            return MailResult(correlation_id="x", outcome=MailOutcome.FAILED, sent=False, error="boom")

    import app.services.supplier_invitation_service as svc

    monkeypatch.setattr(svc, "get_email_client", lambda db=None: _AlwaysFails())

    admin = _admin()
    sup = _supplier(api_client, admin)
    user = api_client.post(
        f"/api/birthday/suppliers/{sup['id']}/users",
        json={"email": "fails@invite.example.com", "send_invitation": False}, headers=admin,
    ).json()

    resp = api_client.post(
        f"/api/birthday/suppliers/{sup['id']}/users/{user['id']}/invite", headers=admin,
    )
    assert resp.status_code == 200  # not a 500 — a truthful, structured failure
    body = resp.json()
    assert body["sent"] is False
    assert "boom" in body["detail"]

    # invited_at/invite_count must NOT advance on a failed send.
    got = api_client.get(f"/api/birthday/suppliers/{sup['id']}/users", headers=admin).json()[0]
    assert got["invited_at"] is None
    assert got["invite_count"] == 0


def test_create_reports_invite_failure_without_failing_the_creation(api_client, db, monkeypatch):
    from mail_client_py import MailOutcome, MailResult

    class _AlwaysFails:
        def send(self, *, to, subject, body, correlation_id=None, content_type="Text"):
            return MailResult(correlation_id="x", outcome=MailOutcome.FAILED, sent=False, error="down")

    import app.services.supplier_invitation_service as svc

    monkeypatch.setattr(svc, "get_email_client", lambda db=None: _AlwaysFails())

    admin = _admin()
    sup = _supplier(api_client, admin)
    resp = api_client.post(
        f"/api/birthday/suppliers/{sup['id']}/users",
        json={"email": "partial@invite.example.com"}, headers=admin,
    )
    assert resp.status_code == 201  # the user WAS created
    body = resp.json()
    assert "could not be sent" in body["invitation_detail"]
    assert body["invited_at"] is None


# --- content: recipient, URL, no secrets -----------------------------------

def test_invitation_email_content(api_client, db, monkeypatch):
    captured = {}

    class _Capture:
        def send(self, *, to, subject, body, correlation_id=None, content_type="Text"):
            from mail_client_py import MailOutcome, MailResult

            captured["to"] = to
            captured["subject"] = subject
            captured["body"] = body
            captured["content_type"] = content_type
            return MailResult(correlation_id="x", outcome=MailOutcome.SUBMITTED, sent=True)

    import app.services.supplier_invitation_service as svc

    monkeypatch.setattr(svc, "get_email_client", lambda db=None: _Capture())
    monkeypatch.setenv("SUPPLIER_PUBLIC_BASE_URL", "https://supplierportal-dev.dijitalteam.com")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        admin = _admin()
        sup = _supplier(api_client, admin, name="Content Test Co")
        api_client.post(
            f"/api/birthday/suppliers/{sup['id']}/users",
            json={"email": "content@invite.example.com", "full_name": "Content Person"},
            headers=admin,
        )
    finally:
        get_settings.cache_clear()

    assert captured["to"] == "content@invite.example.com"
    assert captured["subject"] == "You're invited to the DIJI Birthday Supplier Portal"
    assert captured["content_type"] == "HTML"
    assert "Content Test Co" in captured["body"]
    assert "content@invite.example.com" in captured["body"]
    assert "https://supplierportal-dev.dijitalteam.com" in captured["body"]
    # never anything token/secret-shaped
    assert "access_token" not in captured["body"]
    assert "client_secret" not in captured["body"].lower()
    assert "Bearer" not in captured["body"]


# --- authorization -----------------------------------------------------

def test_invite_requires_manage_permission(api_client, db):
    read_only = headers_for(971, role="BIRTHDAY_USER")  # no birthday.suppliers.manage
    admin = _admin()
    sup = _supplier(api_client, admin)
    user = api_client.post(
        f"/api/birthday/suppliers/{sup['id']}/users",
        json={"email": "guarded@invite.example.com", "send_invitation": False}, headers=admin,
    ).json()

    resp = api_client.post(
        f"/api/birthday/suppliers/{sup['id']}/users/{user['id']}/invite", headers=read_only,
    )
    assert resp.status_code == 403
