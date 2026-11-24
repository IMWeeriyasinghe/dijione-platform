"""'Refresh contact from People' — explicit, per-order remediation for legacy
orders whose contact snapshot predates snapshotting. Fills only EMPTY fields."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.integrations.people_source.client import EmployeeSourceClient, EmployeeSourceUnavailableError
from app.integrations.people_source.schemas import EmployeeRecord
from app.models.birthday_order import BirthdayOrder
from app.models.order_event import OrderEvent
from app.models.supplier import Supplier
from app.models.supplier_communication import SupplierCommunication
from tests.conftest import headers_for

ADMIN = 820
MOBILE = "+94 77 111 2222"
HOME = "+94 11 333 4444"


class _People(EmployeeSourceClient):
    def __init__(self, mobile=None, home=None, *, missing=False, down=False):
        self.mobile, self.home, self.missing, self.down = mobile, home, missing, down

    def list_active_employees(self):
        return []

    def get_employee(self, employee_id):
        if self.down:
            raise EmployeeSourceUnavailableError("down")
        if self.missing:
            return None
        d = date.today() + timedelta(days=8)
        return EmployeeRecord(
            id=employee_id, employee_number="1", display_name="X", work_email="x.y@dijitalteam.com",
            birth_month=d.month, birth_day=d.day, department="D", office_location="Colombo",
            employment_status="Active", hire_date="2015-01-01", mobile_phone=self.mobile, home_phone=self.home,
        )


@pytest.fixture
def people(monkeypatch):
    def _set(**kw):
        src = _People(**kw)
        monkeypatch.setattr("app.services.contact_refresh_service.get_employee_source", lambda: src)
        return src

    return _set


_seq = iter(range(1, 10_000))


def _order(db, **kw):
    sup = Supplier(name=f"S{next(_seq)}", primary_contact_email="o@s.example.com", status="ACTIVE")
    db.add(sup)
    db.commit()
    n = next(_seq)
    d = date.today() + timedelta(days=10)
    fields = dict(
        order_reference=f"BDAY-CR{n}-2026-{n:05d}", employee_id=f"cr-{n}", employee_name="X Y",
        employee_email="x.y@dijitalteam.com", birthday_date=d, birthday_year=d.year, office_location="Colombo",
        quantity=1, status="PENDING_VERIFICATION", supplier_id=sup.id, delivery_date=d - timedelta(days=1),
        address_verification_status="NOT_CHECKED", delivery_address_line1="1 Main Street", delivery_city="Colombo",
        delivery_address_source="BAMBOOHR", birthday_greeting="Happy Birthday X!",
    )
    fields.update(kw)
    order = BirthdayOrder(**fields)
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def _post(api_client, order, role="BIRTHDAY_ADMIN", uid=ADMIN):
    return api_client.post(f"/api/birthday/orders/{order.id}/refresh-contact", headers=headers_for(uid, role=role))


def test_legacy_order_gets_mobile_and_delivery_default(api_client, db, people):
    people(mobile=MOBILE)
    order = _order(db)
    admin = headers_for(ADMIN, role="BIRTHDAY_ADMIN")
    assert api_client.get(f"/api/birthday/orders/{order.id}", headers=admin).json()["contact_refreshable"]
    resp = _post(api_client, order)
    assert resp.status_code == 200
    body = resp.json()
    assert body["employee_mobile_phone"] == MOBILE and body["employee_home_phone"] is None
    assert body["delivery_contact_phone"] == MOBILE
    assert body["contact_refreshable"] is True  # home is still empty, so it can be refreshed again


def test_mobile_and_secondary_both_populated(api_client, db, people):
    people(mobile=MOBILE, home=HOME)
    body = _post(api_client, _order(db)).json()
    assert (body["employee_mobile_phone"], body["employee_home_phone"]) == (MOBILE, HOME)
    assert body["delivery_contact_phone"] == MOBILE
    assert body["contact_refreshable"] is False  # nothing left to refresh


def test_secondary_is_the_default_when_mobile_is_absent(api_client, db, people):
    people(home=HOME)
    body = _post(api_client, _order(db)).json()
    assert body["employee_mobile_phone"] is None and body["employee_home_phone"] == HOME
    assert body["delivery_contact_phone"] == HOME


def test_existing_snapshot_is_never_overwritten(api_client, db, people):
    people(mobile="+94 70 999 9999", home="+94 70 888 8888")
    order = _order(db, employee_mobile_phone=MOBILE, delivery_contact_phone=MOBILE)
    body = _post(api_client, order).json()
    assert body["employee_mobile_phone"] == MOBILE  # kept
    assert body["employee_home_phone"] == "+94 70 888 8888"  # only the empty one filled
    assert body["delivery_contact_phone"] == MOBILE


def test_manually_selected_delivery_contact_is_never_overwritten(api_client, db, people):
    people(mobile=MOBILE)
    manual = "+94 71 000 0000"
    body = _post(api_client, _order(db, delivery_contact_phone=manual)).json()
    assert body["employee_mobile_phone"] == MOBILE
    assert body["delivery_contact_phone"] == manual


def test_nothing_to_refresh_when_both_captured(api_client, db, people):
    people(mobile="+94 70 999 9999")
    order = _order(db, employee_mobile_phone=MOBILE, employee_home_phone=HOME)
    resp = _post(api_client, order)
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "NOTHING_TO_REFRESH"


def test_released_order_cannot_be_refreshed(api_client, db, people):
    people(mobile=MOBILE)
    order = _order(db, status="SENT_TO_SUPPLIER", released_at=datetime.now(UTC))
    resp = _post(api_client, order)
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "ALREADY_RELEASED"
    db.refresh(order)
    assert order.employee_mobile_phone is None
    got = api_client.get(f"/api/birthday/orders/{order.id}", headers=headers_for(ADMIN, role="BIRTHDAY_ADMIN")).json()
    assert got["contact_refreshable"] is False


def test_missing_employee_identity_fails_safely(api_client, db, people):
    people(mobile=MOBILE)
    order = _order(db, employee_id="  ")
    resp = _post(api_client, order)
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "NO_EMPLOYEE_IDENTITY"


@pytest.mark.parametrize(
    ("kw", "status_code", "code"),
    [
        ({"down": True}, 503, "PEOPLE_UNAVAILABLE"),
        ({"missing": True}, 409, "EMPLOYEE_NOT_FOUND"),
        ({}, 409, "NO_PHONE"),
        ({"mobile": "  ", "home": ""}, 409, "NO_PHONE"),
    ],
)
def test_people_failures_are_non_destructive(api_client, db, people, kw, status_code, code):
    people(**kw)
    order = _order(db)
    resp = _post(api_client, order)
    assert resp.status_code == status_code and resp.json()["detail"]["code"] == code
    db.refresh(order)
    assert order.employee_mobile_phone is None and order.employee_home_phone is None
    assert order.delivery_contact_phone is None
    assert db.query(OrderEvent).filter_by(order_id=order.id, event_type="EMPLOYEE_CONTACT_REFRESHED").count() == 0


def test_refresh_changes_nothing_else_sends_no_email_and_audits_without_numbers(api_client, db, people):
    people(mobile=MOBILE, home=HOME)
    order = _order(db)
    before = {
        c: getattr(order, c)
        for c in (
            "delivery_address_line1", "delivery_city", "delivery_address_source", "address_verification_status",
            "supplier_id", "delivery_date", "status", "released_at", "birthday_greeting", "quantity",
        )
    }
    comms_before = db.query(SupplierCommunication).count()
    assert _post(api_client, order).status_code == 200
    db.refresh(order)
    assert {c: getattr(order, c) for c in before} == before
    assert db.query(SupplierCommunication).count() == comms_before
    events = db.query(OrderEvent).filter_by(order_id=order.id, event_type="EMPLOYEE_CONTACT_REFRESHED").all()
    assert len(events) == 1
    ev = events[0]
    assert ev.actor_id == ADMIN and ev.actor_type == "USER"
    assert "employee_mobile_phone" in ev.detail and "delivery_contact_phone" in ev.detail
    assert MOBILE not in ev.detail and HOME not in ev.detail and "+94" not in ev.detail


def test_permissions_and_supplier_isolation(api_client, db, people):
    people(mobile=MOBILE)
    order = _order(db)
    assert api_client.post(f"/api/birthday/orders/{order.id}/refresh-contact").status_code in (401, 403)
    viewer = _post(api_client, order, role="BIRTHDAY_USER", uid=821)
    assert viewer.status_code == 403
    db.refresh(order)
    assert order.employee_mobile_phone is None
    from tests.conftest import supplier_headers_for

    sup = db.get(Supplier, order.supplier_id)
    resp = api_client.post(f"/api/birthday/orders/{order.id}/refresh-contact", headers=supplier_headers_for(db, sup))
    assert resp.status_code in (401, 403)
