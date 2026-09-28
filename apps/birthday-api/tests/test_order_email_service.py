"""Phase D order-email-service tests: rendering (incl. the critical
INTERNAL_NOTE isolation requirement, plan §11) and the send success/failure
paths against MockGraphEmailClient."""

from datetime import date, timedelta

from tests.conftest import headers_for


def _make_order(db, *, supplier_contact_email="orders@supplier.example.com", address_verification_status="VERIFIED"):
    from app.models.birthday_order import BirthdayOrder
    from app.models.special_requirement import SpecialRequirement
    from app.models.supplier import Supplier

    supplier = Supplier(
        name="Test Supplier", primary_contact_email=supplier_contact_email, lead_time_days=2,
    )
    db.add(supplier)
    db.flush()

    order = BirthdayOrder(
        order_reference="BDAY-EMP1-2026-00001",
        employee_id="emp-1",
        employee_name="Alex Doe",
        employee_email="alex@example.com",
        birthday_date=date.today() + timedelta(days=10),
        birthday_year=(date.today() + timedelta(days=10)).year,
        office_location="Colombo",
        quantity=2,
        # Sendable status (plan §K "verification is the approval" — there
        # is no separate approval gate any more, only a status check).
        status="PENDING_VERIFICATION",
        supplier_id=supplier.id,
        # Defaults to VERIFIED so pre-existing send/resend tests (whose
        # focus is the email flow, not the address-verification gate) keep
        # passing; the gate itself is exercised by
        # test_send_blocked_when_address_not_verified below.
        address_verification_status=address_verification_status,
    )
    db.add(order)
    db.flush()

    db.add(
        SpecialRequirement(
            order_id=order.id, kind="SUPPLIER_INSTRUCTION", text="Write 'Happy Birthday Alex' on the cake",
        )
    )
    db.add(
        SpecialRequirement(
            order_id=order.id, kind="INTERNAL_NOTE", text="Employee is allergic to nuts — do not mention to supplier",
        )
    )
    db.commit()
    db.refresh(order)
    return order


def test_render_supplier_email_includes_order_reference(db):
    from app.services.order_email_service import render_supplier_email

    order = _make_order(db)
    subject, html_body, text_body = render_supplier_email(order)
    for body in (html_body, text_body):
        assert order.order_reference in body
        assert order.employee_name in body
        assert order.office_location in body
        assert str(order.quantity) in body
    assert order.order_reference in subject
    # Business-format date ("8 October 2026"), never the raw ISO string.
    expected_date = f"{order.birthday_date.day} {order.birthday_date.strftime('%B %Y')}"
    assert expected_date in html_body
    assert expected_date in text_body
    assert order.birthday_date.isoformat() not in html_body


def test_render_supplier_email_excludes_internal_notes(db):
    from app.services.order_email_service import render_supplier_email

    order = _make_order(db)
    subject, html_body, text_body = render_supplier_email(order)

    # Plain text carries the instruction verbatim; the HTML body carries it
    # HTML-escaped (apostrophes become &#x27;) — check a substring with no
    # special characters so both are exercised without over-specifying the
    # HTML escaping's exact form.
    assert "Write 'Happy Birthday Alex' on the cake" in text_body
    assert "Happy Birthday Alex" in html_body
    for body in (html_body, text_body):
        assert "allergic to nuts" not in body
    assert "allergic to nuts" not in subject


def test_render_supplier_email_subject_retains_order_reference_and_says_new(db):
    from app.services.order_email_service import render_supplier_email

    order = _make_order(db)
    subject, _html, _text = render_supplier_email(order)
    assert subject == f"[{order.order_reference}] New Birthday Cake Order — {order.employee_name}"


def test_render_supplier_email_omits_special_instructions_section_when_absent(db):
    from app.services.order_email_service import render_supplier_email
    from app.models.special_requirement import SpecialRequirement

    order = _make_order(db)
    # Strip the SUPPLIER_INSTRUCTION row _make_order seeds, keep only the
    # INTERNAL_NOTE — no supplier-visible instruction should render at all.
    db.query(SpecialRequirement).filter(
        SpecialRequirement.order_id == order.id,
        SpecialRequirement.kind == "SUPPLIER_INSTRUCTION",
    ).delete()
    db.commit()
    db.refresh(order)

    _subject, html_body, text_body = render_supplier_email(order)
    assert "Special Instructions" not in html_body
    assert "Special Instructions" not in text_body


def test_render_supplier_email_deep_link_uses_supplier_public_base_url(db, monkeypatch):
    from app.core.config import get_settings
    from app.services.order_email_service import render_supplier_email

    monkeypatch.setenv("SUPPLIER_PUBLIC_BASE_URL", "https://supplierportal-dev.dijitalteam.com")
    get_settings.cache_clear()
    try:
        order = _make_order(db)
        _subject, html_body, text_body = render_supplier_email(order)
        expected_url = f"https://supplierportal-dev.dijitalteam.com/orders/{order.id}"
        assert expected_url in html_body
        assert expected_url in text_body
        assert 'View Order' in html_body
        # The order's numeric PK, never anything token/secret-shaped, appears
        # in the link — and nothing resembling a bearer token does.
        assert "access_token" not in html_body
        assert "Bearer" not in html_body
    finally:
        get_settings.cache_clear()


def test_render_supplier_email_no_portal_url_configured_omits_cta_gracefully(db, monkeypatch):
    from app.core.config import get_settings
    from app.services.order_email_service import render_supplier_email

    monkeypatch.setenv("SUPPLIER_PUBLIC_BASE_URL", "")
    get_settings.cache_clear()
    try:
        order = _make_order(db)
        _subject, html_body, _text = render_supplier_email(order)
        assert "View Order" not in html_body
        assert "/orders/" not in html_body
    finally:
        get_settings.cache_clear()


def test_render_supplier_email_unassigned_office_shown_as_to_be_confirmed(db):
    from app.models.birthday_order import BirthdayOrder
    from app.services.order_email_service import render_supplier_email

    order = _make_order(db)
    order.office_location = "Unassigned Office"
    db.commit()
    db.refresh(order)

    _subject, html_body, text_body = render_supplier_email(order)
    assert "Unassigned Office" not in html_body
    assert "Unassigned Office" not in text_body
    assert "To be confirmed" in html_body
    assert "To be confirmed" in text_body


def test_render_supplier_email_real_office_location_passed_through(db):
    """The 'Unassigned Office' substitution must not mask a genuinely-set
    location — this is a display fix for one specific placeholder value,
    not a rewrite of whatever the employee's real office happens to be."""
    from app.services.order_email_service import render_supplier_email

    order = _make_order(db)  # office_location="Colombo" from the fixture
    _subject, html_body, text_body = render_supplier_email(order)
    assert "Colombo" in html_body
    assert "Colombo" in text_body
    assert "To be confirmed" not in html_body


def test_send_order_to_supplier_success(db):
    from app.core.constants import OrderStatus
    from app.services.order_email_service import send_order_to_supplier

    order = _make_order(db)
    updated = send_order_to_supplier(db, order, actor_id=1)

    assert updated.status == OrderStatus.SENT_TO_SUPPLIER.value
    assert len(updated.communications) == 1
    comm = updated.communications[0]
    assert comm.status == "SENT"
    # message_id now stores MailClient's own generated correlation id (a
    # plain UUID, generated once centrally rather than per-transport) —
    # not a Graph-native id, and no longer prefixed by the transport.
    assert comm.message_id
    assert comm.transport_outcome == "SIMULATED"


def test_send_order_to_supplier_failure_moves_to_requires_attention(db):
    from app.core.constants import OrderStatus
    from app.services.order_email_service import send_order_to_supplier

    order = _make_order(db, supplier_contact_email="")  # forces MockGraphEmailClient failure
    updated = send_order_to_supplier(db, order, actor_id=1)

    assert updated.status == OrderStatus.REQUIRES_ATTENTION.value
    assert len(updated.communications) == 1
    comm = updated.communications[0]
    assert comm.status == "FAILED"
    assert comm.last_error

    event_types = [e.event_type for e in updated.events]
    assert "EMAIL_FAILED" in event_types


def test_send_order_to_supplier_failure_defers_notification_until_retries_exhausted(db, platform_calls):
    """Phase 1 §1.3: the first failure parks the order and schedules a
    backoff retry — the BIRTHDAY_ADMIN notification is deferred until the
    retry sweep exhausts max_attempts."""
    from datetime import UTC, datetime, timedelta

    from app.models.supplier_communication import SupplierCommunication
    from app.services.order_email_service import retry_failed_outbound, send_order_to_supplier

    order = _make_order(db, supplier_contact_email="")
    send_order_to_supplier(db, order, actor_id=1)

    assert order.status == "REQUIRES_ATTENTION"
    comm = db.query(SupplierCommunication).filter_by(order_id=order.id).one()
    assert comm.status == "FAILED" and comm.next_retry_at is not None
    assert platform_calls["broadcasts"] == []  # not yet

    comm.max_attempts = 2
    db.commit()
    now = datetime.now(UTC)
    for _ in range(4):
        now += timedelta(hours=6)
        retry_failed_outbound(db, now=now)

    assert any(b["role"] == "BIRTHDAY_ADMIN" for b in platform_calls["broadcasts"])


def test_send_order_to_supplier_no_supplier_raises(db):
    from app.models.birthday_order import BirthdayOrder
    from app.services.order_email_service import NoSupplierAssignedError, send_order_to_supplier

    order = BirthdayOrder(
        order_reference="BDAY-EMP2-2026-00001",
        employee_id="emp-2",
        employee_name="Sam Roe",
        employee_email="sam@example.com",
        birthday_date=date.today() + timedelta(days=10),
        birthday_year=(date.today() + timedelta(days=10)).year,
        office_location="Colombo",
        status="PENDING_VERIFICATION",
        supplier_id=None,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    try:
        send_order_to_supplier(db, order, actor_id=1)
        raise AssertionError("expected NoSupplierAssignedError")
    except NoSupplierAssignedError:
        pass


def test_resend_after_failure_succeeds(db):
    from app.core.constants import OrderStatus
    from app.models.supplier import Supplier
    from app.services.order_email_service import resend_order_to_supplier, send_order_to_supplier

    order = _make_order(db, supplier_contact_email="")
    order = send_order_to_supplier(db, order, actor_id=1)
    assert order.status == OrderStatus.REQUIRES_ATTENTION.value

    # Fix the supplier contact and retry.
    supplier = db.get(Supplier, order.supplier_id)
    supplier.primary_contact_email = "fixed@supplier.example.com"
    db.commit()

    order = resend_order_to_supplier(db, order, actor_id=1)
    assert order.status == OrderStatus.SENT_TO_SUPPLIER.value
    assert len(order.communications) == 2


def test_send_to_supplier_endpoint(api_client, db):
    from app.models.supplier import Supplier

    supplier = Supplier(name="Route Test Supplier", primary_contact_email="rt@supplier.example.com")
    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    headers = headers_for(40, role="BIRTHDAY_ADMIN")
    payload = {
        "employee_id": "emp-800",
        "employee_name": "Priya Kumar",
        "employee_email": "priya@example.com",
        "birthday_date": str(date.today() + timedelta(days=15)),
        "office_location": "Colombo",
    }
    created = api_client.post("/api/birthday/orders", json=payload, headers=headers).json()
    order_id = created["id"]

    # Assign the supplier directly (no dedicated reassign endpoint in scope).
    from app.models.birthday_order import BirthdayOrder

    order = db.get(BirthdayOrder, order_id)
    order.supplier_id = supplier.id
    order.address_verification_status = "VERIFIED"
    order.status = "PENDING_VERIFICATION"
    db.commit()

    resp = api_client.post(f"/api/birthday/orders/{order_id}/send-to-supplier", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "SENT_TO_SUPPLIER"


def test_send_to_supplier_blocked_when_address_not_verified(api_client, db):
    """Cake-order gate (plan requirement #10): an otherwise-sendable order
    must not progress to SENT_TO_SUPPLIER until P&C has verified the
    delivery address. The order stays visible/actionable (409, not a
    silent drop) — see AddressNotVerifiedError."""
    from app.models.supplier import Supplier

    supplier = Supplier(name="Gate Test Supplier", primary_contact_email="gate@supplier.example.com")
    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    headers = headers_for(42, role="BIRTHDAY_ADMIN")
    payload = {
        "employee_id": "emp-900",
        "employee_name": "Gate Test",
        "employee_email": "gate.test@example.com",
        "birthday_date": str(date.today() + timedelta(days=15)),
        "office_location": "Colombo",
    }
    created = api_client.post("/api/birthday/orders", json=payload, headers=headers).json()
    order_id = created["id"]
    assert created["address_verification_status"] == "NOT_CHECKED"  # model default

    from app.models.birthday_order import BirthdayOrder

    order = db.get(BirthdayOrder, order_id)
    order.supplier_id = supplier.id
    order.status = "PENDING_VERIFICATION"
    db.commit()

    resp = api_client.post(f"/api/birthday/orders/{order_id}/send-to-supplier", headers=headers)
    assert resp.status_code == 409
    assert "address" in resp.json()["detail"].lower()


def test_send_to_supplier_forbidden_without_permission(api_client, db):
    headers = headers_for(41, role="BIRTHDAY_ADMIN")
    payload = {
        "employee_id": "emp-801",
        "employee_name": "Nimal Silva",
        "employee_email": "nimal@example.com",
        "birthday_date": str(date.today() + timedelta(days=15)),
        "office_location": "Colombo",
    }
    created = api_client.post("/api/birthday/orders", json=payload, headers=headers).json()

    resp = api_client.post(
        f"/api/birthday/orders/{created['id']}/send-to-supplier",
        headers=headers_for(42, role="BIRTHDAY_USER"),
    )
    assert resp.status_code == 403
