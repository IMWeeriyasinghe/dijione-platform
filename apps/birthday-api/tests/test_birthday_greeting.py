"""Requirement 6 (default editable Birthday greeting) and the contact-default
cases from Requirement 5."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.core.greeting import (
    DEFAULT_GREETING_TEMPLATE,
    default_greeting,
    default_greeting_for,
    first_name_from_email,
    greeting_first_name,
)
from app.integrations.people_source.client import EmployeeSourceClient
from app.integrations.people_source.schemas import EmployeeRecord
from app.models.birthday_order import BirthdayOrder
from app.models.detection_config import BirthdayDetectionConfig
from app.models.supplier import Supplier
from app.services.detection_service import run_daily_scan
from app.services.order_email_service import render_supplier_email, send_order_to_supplier
from tests.conftest import headers_for, supplier_headers_for

ADMIN = 810
EXPECTED = (
    "Happy Birthday Nirmani!\n\n"
    "On behalf of everyone at Dijital Team, we wanted to wish you a wonderful day "
    "and best wishes for the year ahead!\n\n"
    "All the very best!!\n\n"
    "- Peter Ward"
)


# -- first-name derivation (work email, not BambooHR names) -----------------

@pytest.mark.parametrize(
    ("email", "expected"),
    [
        ("nirmani.dahanayaka@dijitalteam.com", "Nirmani"),
        ("MADUSHANKA.WEERIYASINGHE@DIJITALTEAM.COM", "Madushanka"),
        ("imaz_hameed@dijitalteam.com", "Imaz"),
        ("peter-ward@dijitalteam.com", "Peter"),
        ("anna+tag@dijitalteam.com", "Anna"),
        ("sam@dijitalteam.com", "Sam"),
        ("john2.smith@dijitalteam.com", "John"),
    ],
)
def test_first_name_from_email(email, expected):
    assert first_name_from_email(email) == expected


@pytest.mark.parametrize(
    "email",
    [None, "", "   ", "@dijitalteam.com", "12345.x@dijitalteam.com", "a.b@dijitalteam.com", "..@x.com"],
)
def test_unusable_email_has_no_name(email):
    assert first_name_from_email(email) is None


def test_falls_back_to_display_name_first_usable_word():
    assert greeting_first_name(None, "ravindu perera") == "Ravindu"
    assert greeting_first_name("12345@x.com", "  K. Nimal  Silva") == "Nimal"
    assert greeting_first_name("nirmani.d@x.com", "Someone Else") == "Nirmani"  # email wins over BambooHR name


def test_no_usable_name_never_produces_a_blank_salutation():
    text = default_greeting_for(None, "")
    assert text.startswith("Happy Birthday!\n")
    assert "Happy Birthday !" not in text and "None" not in text and "{first_name}" not in text


# -- the default greeting text ------------------------------------------------

def test_default_greeting_exact_text_and_line_breaks():
    assert default_greeting("Nirmani") == EXPECTED
    assert default_greeting_for("nirmani.dahanayaka@dijitalteam.com", "Wrong Name") == EXPECTED
    assert "Dijital Team" in EXPECTED and "{first_name}" in DEFAULT_GREETING_TEMPLATE
    assert EXPECTED.count("\n\n") == 3  # four paragraphs


# -- persistence -----------------------------------------------------------------

def _supplier(db):
    s = Supplier(name="Greeting Bakes", primary_contact_email="orders@greeting.example.com", status="ACTIVE")
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


_seq = iter(range(1, 10_000))


def _order(db, supplier, *, greeting="UNSET", status="PENDING_VERIFICATION", verified=True,
           email="nirmani.dahanayaka@dijitalteam.com", name="N Dahanayaka"):
    n = next(_seq)
    order = BirthdayOrder(
        order_reference=f"BDAY-GR{n}-2026-{n:05d}", employee_id=f"gr-{n}", employee_name=name,
        employee_email=email, birthday_date=date.today() + timedelta(days=10),
        birthday_year=(date.today() + timedelta(days=10)).year, office_location="Colombo", quantity=1,
        status=status, supplier_id=supplier.id, delivery_date=date.today() + timedelta(days=9),
        address_verification_status="VERIFIED" if verified else "NOT_CHECKED",
        delivery_address_line1="1 Main Street", delivery_city="Colombo",
        released_at=datetime.now(UTC) if status == "SENT_TO_SUPPLIER" else None,
    )
    if greeting != "UNSET":
        order.birthday_greeting = greeting
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def test_new_order_gets_the_default_greeting(db):
    from app.core.constants import OrderStatus
    from app.services.order_service import create_or_get_order

    order, _ = create_or_get_order(
        db, employee_id="g-1", employee_number="1", employee_name="X", employee_email="nirmani.dahanayaka@dijitalteam.com",
        order_reference="BDAY-G1-2026-00001", birthday_date=date.today() + timedelta(days=9),
        birthday_year=date.today().year, office_location="Colombo", lead_time_days=9, lead_time_class="NORMAL",
        status=OrderStatus.PENDING_VERIFICATION, requires_admin_review=False, hold_reason=None, supplier_id=None,
    )
    assert order.birthday_greeting == EXPECTED


def test_edit_persists_and_is_not_regenerated_on_load_or_other_edits(api_client, db):
    sup = _supplier(db)
    order = _order(db, sup, greeting=EXPECTED)
    admin = headers_for(ADMIN, role="BIRTHDAY_ADMIN")
    edited = "Happy Birthday Nirmani!\r\n\r\nHave a wonderful day.   \r\n\r\n- The Team  \r\n"

    resp = api_client.patch(f"/api/birthday/orders/{order.id}", json={"birthday_greeting": edited}, headers=admin)
    assert resp.status_code == 200
    stored = "Happy Birthday Nirmani!\n\nHave a wonderful day.\n\n- The Team"
    assert resp.json()["birthday_greeting"] == stored

    for _ in range(2):  # loading never regenerates it
        assert api_client.get(f"/api/birthday/orders/{order.id}", headers=admin).json()["birthday_greeting"] == stored
    other = api_client.patch(f"/api/birthday/orders/{order.id}", json={"quantity": 3}, headers=admin)
    assert other.status_code == 200 and other.json()["birthday_greeting"] == stored  # other edits keep it
    api_client.patch(f"/api/birthday/orders/{order.id}/delivery-address", json={"delivery_city": "Kandy"}, headers=admin)
    assert api_client.get(f"/api/birthday/orders/{order.id}", headers=admin).json()["birthday_greeting"] == stored


def test_legacy_null_greeting_is_safe_and_suggests_without_saving(api_client, db):
    sup = _supplier(db)
    order = _order(db, sup, greeting=None)
    body = api_client.get(f"/api/birthday/orders/{order.id}", headers=headers_for(ADMIN, role="BIRTHDAY_ADMIN")).json()
    assert body["birthday_greeting"] is None and body["suggested_birthday_greeting"] == EXPECTED
    db.expire_all()
    assert db.get(BirthdayOrder, order.id).birthday_greeting is None  # viewing did not write


def test_greeting_validation_and_permission(api_client, db):
    sup = _supplier(db)
    order = _order(db, sup)
    admin = headers_for(ADMIN, role="BIRTHDAY_ADMIN")
    assert api_client.patch(f"/api/birthday/orders/{order.id}", json={"birthday_greeting": "x" * 2001},
                            headers=admin).status_code == 422
    assert api_client.patch(f"/api/birthday/orders/{order.id}", json={"birthday_greeting": "Hi"},
                            headers=headers_for(811, role="BIRTHDAY_USER")).status_code == 403
    cleared = api_client.patch(f"/api/birthday/orders/{order.id}", json={"birthday_greeting": "  \n "}, headers=admin)
    assert cleared.status_code == 200 and cleared.json()["birthday_greeting"] == ""


def test_legacy_order_is_initialised_at_release_but_edited_or_cleared_is_kept(db):
    sup = _supplier(db)
    legacy = _order(db, sup, greeting=None)
    edited = _order(db, sup, greeting="Custom words")
    cleared = _order(db, sup, greeting="")
    for order in (legacy, edited, cleared):
        send_order_to_supplier(db, order, actor_id=1)
    db.expire_all()
    assert db.get(BirthdayOrder, legacy.id).birthday_greeting == EXPECTED
    assert db.get(BirthdayOrder, edited.id).birthday_greeting == "Custom words"
    assert db.get(BirthdayOrder, cleared.id).birthday_greeting == ""


# -- supplier visibility --------------------------------------------------------------

def test_assigned_supplier_sees_exact_released_greeting_read_only(api_client, db):
    sup = _supplier(db)
    other = Supplier(name="Other Bakes", status="ACTIVE")
    db.add(other)
    db.commit()
    order = _order(db, sup, greeting="Line one\n\nLine two", status="SENT_TO_SUPPLIER")
    h = supplier_headers_for(db, sup)
    detail = api_client.get(f"/api/birthday/portal/orders/{order.id}", headers=h).json()
    assert detail["birthday_greeting"] == "Line one\n\nLine two"
    assert "birthday_greeting" not in api_client.get("/api/birthday/portal/orders", headers=h).json()["items"][0]
    assert api_client.get(f"/api/birthday/portal/orders/{order.id}", headers=supplier_headers_for(db, other)).status_code == 404
    attempt = api_client.patch(f"/api/birthday/orders/{order.id}", json={"birthday_greeting": "mine"}, headers=h)
    assert attempt.status_code in (401, 403)  # suppliers cannot edit it


def test_supplier_sees_nothing_for_cleared_or_legacy_greeting(api_client, db):
    sup = _supplier(db)
    h = supplier_headers_for(db, sup)
    for greeting in ("", None):
        order = _order(db, sup, greeting=greeting, status="SENT_TO_SUPPLIER")
        assert api_client.get(f"/api/birthday/portal/orders/{order.id}", headers=h).json()["birthday_greeting"] is None


def test_changing_the_greeting_after_release_is_not_silent(api_client, db):
    sup = _supplier(db)
    order = _order(db, sup, greeting="Old", status="SENT_TO_SUPPLIER")
    api_client.patch(f"/api/birthday/orders/{order.id}", json={"birthday_greeting": "New"},
                     headers=headers_for(ADMIN, role="BIRTHDAY_ADMIN"))
    from app.models.order_event import OrderEvent

    events = db.query(OrderEvent).filter_by(order_id=order.id, event_type="ORDER_CHANGED_POST_RELEASE").all()
    assert any("greeting" in (e.detail or "") for e in events)


# -- supplier email ------------------------------------------------------------------------

def test_supplier_email_includes_greeting_in_html_and_text_escaped(db):
    sup = _supplier(db)
    order = _order(db, sup, greeting="Happy Birthday <b>Nirmani</b>!\n\n- Peter & Team")
    subject, html, _text = render_supplier_email(order)
    from app.services.supplier_email_template import render_supplier_order_email

    content = render_supplier_order_email(order, [])
    assert "Birthday Greeting" in html
    assert "Hello Greeting Bakes," in html  # the supplier salutation is untouched by the greeting row
    assert "&lt;b&gt;Nirmani&lt;/b&gt;" in html and "<b>Nirmani</b>" not in html  # cannot inject markup
    assert "<br><br>- Peter &amp; Team" in html  # line breaks preserved
    assert "BIRTHDAY GREETING" in content.text_body
    assert "Happy Birthday <b>Nirmani</b>!\n\n- Peter & Team" in content.text_body
    assert subject.startswith(f"[{order.order_reference}]")


def test_supplier_email_omits_the_section_without_a_greeting(db):
    sup = _supplier(db)
    for greeting in ("", None):
        order = _order(db, sup, greeting=greeting)
        _s, html, _t = render_supplier_email(order)
        assert "Birthday Greeting" not in html


# -- Requirement 5: contact defaults come from the People record --------------------------


class _StubSource(EmployeeSourceClient):
    def __init__(self, **phones):
        d = date.today() + timedelta(days=8)
        self.record = EmployeeRecord(
            id="bhr-9001", employee_number="9001", display_name="Zed Example", work_email="zed.example@dijitalteam.com",
            birth_month=d.month, birth_day=d.day, department="D", office_location="Colombo",
            employment_status="Active", hire_date="2015-01-01", **phones,
        )

    def list_active_employees(self):
        return [self.record]

    def get_employee(self, employee_id):
        return self.record


def _config() -> BirthdayDetectionConfig:
    return BirthdayDetectionConfig(
        normal_threshold_days=10, short_notice_threshold_days=5, urgent_threshold_days=2, window_lookback_days=1,
        window_lookahead_days=14, default_quantity=1, verify_buffer_days=2, acknowledgement_sla_hours=24,
        auto_release_enabled=True, supplier_lead_time_days=7,
    )


@pytest.mark.parametrize(
    ("phones", "mobile", "home", "default"),
    [
        (
            {"mobile_phone": "+94 77 600 0001", "home_phone": "+94 11 600 0002"},
            "+94 77 600 0001", "+94 11 600 0002", "+94 77 600 0001",
        ),
        ({"mobile_phone": "+94 77 600 0003"}, "+94 77 600 0003", None, "+94 77 600 0003"),
        ({"home_phone": "+94 11 600 0004"}, None, "+94 11 600 0004", "+94 11 600 0004"),  # secondary used when no primary
        ({}, None, None, None),
    ],
)
def test_scan_snapshots_contacts_and_defaults_the_delivery_contact(db, phones, mobile, home, default):
    db.add(Supplier(name="Scan Bakes", status="ACTIVE"))
    db.commit()
    run_daily_scan(db, _StubSource(**phones), _config())
    order = db.query(BirthdayOrder).filter_by(employee_id="bhr-9001").one()
    assert (order.employee_mobile_phone, order.employee_home_phone, order.delivery_contact_phone) == (mobile, home, default)
    assert order.birthday_greeting == default_greeting("Zed")


def test_an_order_created_before_the_snapshot_existed_stays_empty_until_a_new_order(api_client, db):
    """The observed 2026-11-24 case: People has the numbers but an order created before
    the contact snapshot existed has none. Orders are never rewritten silently."""
    sup = _supplier(db)
    old = _order(db, sup)
    body = api_client.get(f"/api/birthday/orders/{old.id}", headers=headers_for(ADMIN, role="BIRTHDAY_ADMIN")).json()
    assert body["employee_mobile_phone"] is None and body["employee_home_phone"] is None
    assert body["delivery_contact_phone"] is None
    # P&C can still give the supplier a number without touching the address.
    ok = api_client.patch(f"/api/birthday/orders/{old.id}/delivery-address",
                          json={"delivery_contact_phone": "+94 77 700 0001"},
                          headers=headers_for(ADMIN, role="BIRTHDAY_ADMIN"))
    assert ok.status_code == 200 and ok.json()["delivery_contact_phone"] == "+94 77 700 0001"
    assert ok.json()["delivery_address_source"] != "MANUAL_CORRECTION"
