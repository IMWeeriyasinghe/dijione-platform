"""Post-demo increment: P&C email alerts for supplier activity, team-member
contact numbers (snapshot + P&C delivery contact), supplier delivery contact."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from mail_client_py import MailOutcome, MailResult

from app.core.config import get_settings
from app.models.birthday_order import BirthdayOrder
from app.models.detection_config import BirthdayDetectionConfig
from app.models.internal_alert import InternalAlert
from app.models.order_issue import OrderIssue
from app.models.supplier import Supplier
from app.models.supplier_communication import SupplierCommunication
from app.services import internal_alert_service
from tests.conftest import headers_for, supplier_headers_for

ADMIN = 700
RECIPIENTS = "pnc.one@dijitalteam.com, pnc.two@dijitalteam.com"


class _FakeClient:
    def __init__(self, outcome=MailOutcome.SUBMITTED, raises: Exception | None = None):
        self.sent: list[dict] = []
        self.outcome, self.raises = outcome, raises

    def send(self, *, to, subject, body, correlation_id=None, content_type="Text"):
        self.sent.append({"to": to, "subject": subject, "body": body, "content_type": content_type})
        if self.raises:
            raise self.raises
        return MailResult(correlation_id=correlation_id or "c", outcome=self.outcome,
                          sent=self.outcome == MailOutcome.SUBMITTED)


@pytest.fixture
def mail(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr(internal_alert_service, "get_email_client", lambda db=None: client)
    monkeypatch.setenv("BIRTHDAY_INTERNAL_BASE_URL", "https://dijione-dev.dijitalteam.com")
    get_settings.cache_clear()
    yield client
    get_settings.cache_clear()


def _config(db, recipients: str | None = RECIPIENTS):
    cfg = db.query(BirthdayDetectionConfig).first() or BirthdayDetectionConfig()
    cfg.ops_alert_recipients = recipients
    db.add(cfg)
    db.commit()


_seq = iter(range(1, 10_000))


def _order(db, supplier, *, status="SENT_TO_SUPPLIER", verified=True, mobile=None, home=None, chosen=None):
    n = next(_seq)
    o = BirthdayOrder(
        order_reference=f"BDAY-PD{n}-2026-{n:05d}", employee_id=f"pd-{n}", employee_name=f"Team Member {n}",
        employee_email=f"tm{n}@example.com", birthday_date=date.today() + timedelta(days=10),
        birthday_year=(date.today() + timedelta(days=10)).year, office_location="Colombo", quantity=1,
        status=status, supplier_id=supplier.id,
        address_verification_status="VERIFIED" if verified else "NOT_CHECKED",
        delivery_address_line1="1 Main Street", delivery_city="Colombo",
        released_at=datetime.now(UTC) if status != "PENDING_VERIFICATION" else None,
        employee_mobile_phone=mobile, employee_home_phone=home, delivery_contact_phone=chosen,
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


def _suppliers(db):
    a, b = Supplier(name="Kapruka", status="ACTIVE"), Supplier(name="Other Bakes", status="ACTIVE")
    db.add_all([a, b])
    db.commit()
    return a, b


# -- Requirement 1: P&C email alerts ---------------------------------------

def test_supplier_message_persists_and_emails_pnc_with_order_link(api_client, db, mail):
    _config(db)
    sup, _ = _suppliers(db)
    order = _order(db, sup)
    resp = api_client.post(f"/api/birthday/portal/orders/{order.id}/messages", json={"body": "Cake ready at 3pm?"},
                           headers=supplier_headers_for(db, sup))
    assert resp.status_code == 201
    assert db.query(SupplierCommunication).filter_by(order_id=order.id).count() == 1
    assert {m["to"] for m in mail.sent} == {"pnc.one@dijitalteam.com", "pnc.two@dijitalteam.com"}
    sent = mail.sent[0]
    assert sent["subject"] == f"DIJI Birthday — New supplier message for {order.order_reference}"
    assert f"https://dijione-dev.dijitalteam.com/birthday/orders/{order.id}" in sent["body"]
    assert "Cake ready at 3pm?" in sent["body"] and "Kapruka" in sent["body"]
    assert "1 Main Street" not in sent["body"]  # no address in internal alerts
    alerts = db.query(InternalAlert).filter_by(order_id=order.id).all()
    assert len(alerts) == 2 and all(a.status == "SENT" for a in alerts)


def test_supplier_issue_and_cannot_fulfil_alert_and_keep_existing_behaviour(api_client, db, mail):
    _config(db, "pnc.one@dijitalteam.com")
    sup, _ = _suppliers(db)
    issue_order, cnf_order = _order(db, sup), _order(db, sup)
    h = supplier_headers_for(db, sup)

    r1 = api_client.post(f"/api/birthday/portal/orders/{issue_order.id}/issues",
                         json={"type": "DELIVERY_ISSUE", "detail": "Recipient unreachable"}, headers=h)
    assert r1.status_code == 201
    r2 = api_client.post(f"/api/birthday/portal/orders/{cnf_order.id}/issues",
                         json={"type": "CANNOT_FULFIL", "detail": "Out of stock"}, headers=h)
    assert r2.status_code == 201

    db.expire_all()
    assert db.query(OrderIssue).count() == 2
    assert db.get(BirthdayOrder, cnf_order.id).status == "UNABLE_TO_FULFIL"  # unchanged state machine
    subjects = [m["subject"] for m in mail.sent]
    assert f"DIJI Birthday — Supplier issue reported for {issue_order.order_reference}" in subjects
    assert f"DIJI Birthday — Supplier unable to fulfil {cnf_order.order_reference}" in subjects


def test_alert_is_idempotent_per_event_and_recipient(db, mail):
    _config(db, "pnc.one@dijitalteam.com")
    sup, _ = _suppliers(db)
    order = _order(db, sup)
    for _ in range(3):
        internal_alert_service.notify_supplier_activity(
            db, order, event_type=internal_alert_service.EVENT_SUPPLIER_ISSUE, source_key="issue:42", summary="x",
        )
    assert len(mail.sent) == 1
    assert db.query(InternalAlert).filter_by(source_key="issue:42").count() == 1


def test_mail_failure_never_fails_supplier_action_and_is_retried(api_client, db, monkeypatch):
    _config(db, "pnc.one@dijitalteam.com")
    failing = _FakeClient(raises=RuntimeError("graph down"))
    monkeypatch.setattr(internal_alert_service, "get_email_client", lambda db=None: failing)
    sup, _ = _suppliers(db)
    order = _order(db, sup)

    resp = api_client.post(f"/api/birthday/portal/orders/{order.id}/messages", json={"body": "Hello"},
                           headers=supplier_headers_for(db, sup))
    assert resp.status_code == 201
    assert db.query(SupplierCommunication).filter_by(order_id=order.id).count() == 1  # not lost
    alert = db.query(InternalAlert).one()
    assert alert.status == "FAILED" and alert.attempts == 1 and alert.next_retry_at is not None

    ok = _FakeClient()
    monkeypatch.setattr(internal_alert_service, "get_email_client", lambda db=None: ok)
    future = datetime.now(UTC) + timedelta(hours=2)
    assert internal_alert_service.retry_failed_alerts(db, now=future) == {"retried": 1}
    db.expire_all()
    alert = db.query(InternalAlert).one()
    assert alert.status == "SENT" and alert.attempts == 2
    assert ok.sent[0]["subject"].endswith(order.order_reference)
    assert internal_alert_service.retry_failed_alerts(db, now=future) == {"retried": 0}  # no duplicate


def test_retry_gives_up_after_max_attempts(db, monkeypatch):
    _config(db, "pnc.one@dijitalteam.com")
    monkeypatch.setattr(internal_alert_service, "get_email_client",
                        lambda db=None: _FakeClient(outcome=MailOutcome.FAILED))
    sup, _ = _suppliers(db)
    order = _order(db, sup)
    internal_alert_service.notify_supplier_activity(
        db, order, event_type=internal_alert_service.EVENT_SUPPLIER_MESSAGE, source_key="message:1", summary="x",
    )
    for day in range(1, 11):  # each sweep runs well after the previous backoff
        internal_alert_service.retry_failed_alerts(db, now=datetime.now(UTC) + timedelta(days=day))
    alert = db.query(InternalAlert).one()
    assert alert.status == "GAVE_UP" and alert.attempts == 5


def test_no_recipients_configured_means_no_email(api_client, db, mail):
    _config(db, None)
    sup, _ = _suppliers(db)
    order = _order(db, sup)
    api_client.post(f"/api/birthday/portal/orders/{order.id}/messages", json={"body": "Hi"},
                    headers=supplier_headers_for(db, sup))
    assert mail.sent == [] and db.query(InternalAlert).count() == 0


def test_alert_uses_environment_mail_policy(api_client, db, monkeypatch):
    """Through the real factory with the null transport, the send is SIMULATED,
    never a real email — the environment policy is not bypassed."""
    monkeypatch.setenv("MAIL_TRANSPORT", "null")
    get_settings.cache_clear()
    _config(db, "pnc.one@dijitalteam.com")
    sup, _ = _suppliers(db)
    order = _order(db, sup)
    api_client.post(f"/api/birthday/portal/orders/{order.id}/messages", json={"body": "Hi"},
                    headers=supplier_headers_for(db, sup))
    alert = db.query(InternalAlert).one()
    assert alert.transport_outcome == "SIMULATED" and alert.status == "SIMULATED"
    get_settings.cache_clear()


def test_other_supplier_cannot_post_or_trigger_alerts(api_client, db, mail):
    _config(db)
    sup, other = _suppliers(db)
    order = _order(db, sup)
    resp = api_client.post(f"/api/birthday/portal/orders/{order.id}/messages", json={"body": "x"},
                           headers=supplier_headers_for(db, other))
    assert resp.status_code == 404
    assert mail.sent == []


def test_alert_recipient_setting_validation(api_client, db):
    admin = headers_for(ADMIN, role="BIRTHDAY_ADMIN")
    bad = api_client.patch("/api/birthday/config", json={"ops_alert_recipients": "not-an-email"}, headers=admin)
    assert bad.status_code == 422
    ok = api_client.patch("/api/birthday/config",
                          json={"ops_alert_recipients": "B@Dijitalteam.com; a@dijitalteam.com, b@dijitalteam.com"},
                          headers=admin)
    assert ok.status_code == 200
    assert ok.json()["ops_alert_recipients"] == "b@dijitalteam.com\na@dijitalteam.com"
    user = api_client.patch("/api/birthday/config", json={"ops_alert_recipients": "a@dijitalteam.com"},
                            headers=headers_for(701, role="BIRTHDAY_USER"))
    assert user.status_code == 403


# -- Requirement 2: contact numbers snapshot + P&C delivery contact ---------

def test_scan_snapshots_both_contact_numbers_through_people_source(db):
    from app.integrations.people_source.mock_adapter import MockEmployeeSource
    from app.services.detection_service import run_daily_scan

    db.add(Supplier(name="Only Bakes", status="ACTIVE"))
    db.commit()
    cfg = BirthdayDetectionConfig(
        normal_threshold_days=10, short_notice_threshold_days=5, urgent_threshold_days=2,
        window_lookback_days=1, window_lookahead_days=14, default_quantity=1, verify_buffer_days=2,
        acknowledgement_sla_hours=24, auto_release_enabled=True, supplier_lead_time_days=7,
    )
    run_daily_scan(db, MockEmployeeSource(), cfg)
    amara = db.query(BirthdayOrder).filter_by(employee_email="amara.silva@example.com").one()
    assert (amara.employee_mobile_phone, amara.employee_home_phone) == ("+94 77 000 0001", "+94 11 000 0001")
    assert amara.delivery_contact_phone == "+94 77 000 0001"  # mobile is the default
    others = db.query(BirthdayOrder).filter(BirthdayOrder.employee_email != "amara.silva@example.com").all()
    assert others and all(o.employee_mobile_phone is None and o.delivery_contact_phone is None for o in others)


def test_create_order_defaults_contact_to_home_when_no_mobile(db):
    from app.core.constants import OrderStatus
    from app.services.order_service import create_or_get_order

    order, _ = create_or_get_order(
        db, employee_id="c-1", employee_number="1", employee_name="A", employee_email="a@example.com",
        order_reference="BDAY-C1-2026-00001", birthday_date=date.today() + timedelta(days=9),
        birthday_year=date.today().year, office_location="Colombo", lead_time_days=9,
        lead_time_class="NORMAL", status=OrderStatus.PENDING_VERIFICATION, requires_admin_review=False,
        hold_reason=None, supplier_id=None,
        employee_mobile_phone="  ", employee_home_phone="+94 11 222 3333",
    )
    assert order.employee_mobile_phone is None
    assert order.delivery_contact_phone == "+94 11 222 3333"


def test_pnc_sees_both_numbers_and_can_choose_delivery_contact_without_flagging(api_client, db):
    sup, _ = _suppliers(db)
    order = _order(db, sup, status="PENDING_VERIFICATION", verified=False,
                   mobile="+94 77 111 2222", home="+94 11 333 4444", chosen="+94 77 111 2222")
    admin = headers_for(ADMIN, role="BIRTHDAY_ADMIN")
    body = api_client.get(f"/api/birthday/orders/{order.id}", headers=admin).json()
    assert (body["employee_mobile_phone"], body["employee_home_phone"]) == ("+94 77 111 2222", "+94 11 333 4444")

    resp = api_client.patch(f"/api/birthday/orders/{order.id}/delivery-address",
                            json={"delivery_contact_phone": "+94 11 333 4444"}, headers=admin)
    assert resp.status_code == 200
    assert resp.json()["delivery_contact_phone"] == "+94 11 333 4444"
    # Choosing the contact is not an address correction.
    assert resp.json()["delivery_address_source"] != "MANUAL_CORRECTION"

    bad = api_client.patch(f"/api/birthday/orders/{order.id}/delivery-address",
                           json={"delivery_contact_phone": "call me maybe"}, headers=admin)
    assert bad.status_code == 422
    denied = api_client.patch(f"/api/birthday/orders/{order.id}/delivery-address",
                              json={"delivery_contact_phone": "+94 11 333 4444"},
                              headers=headers_for(702, role="BIRTHDAY_USER"))
    assert denied.status_code == 403


def test_historical_order_without_numbers_still_reads(api_client, db):
    sup, _ = _suppliers(db)
    order = _order(db, sup)
    body = api_client.get(f"/api/birthday/orders/{order.id}", headers=headers_for(ADMIN, role="BIRTHDAY_ADMIN")).json()
    assert body["employee_mobile_phone"] is None and body["delivery_contact_phone"] is None


# -- Requirement 3: supplier delivery contact --------------------------------

def test_assigned_supplier_sees_chosen_and_alternative_number_on_detail_only(api_client, db):
    sup, other = _suppliers(db)
    order = _order(db, sup, mobile="+94 77 111 2222", home="+94 11 333 4444", chosen="+94 11 333 4444")
    h = supplier_headers_for(db, sup)
    detail = api_client.get(f"/api/birthday/portal/orders/{order.id}", headers=h).json()
    assert detail["delivery_contact_phone"] == "+94 11 333 4444"
    assert detail["alternative_contact_phone"] == "+94 77 111 2222"

    listing = api_client.get("/api/birthday/portal/orders", headers=h).json()["items"][0]
    assert "delivery_contact_phone" not in listing and "alternative_contact_phone" not in listing

    assert api_client.get(f"/api/birthday/portal/orders/{order.id}",
                          headers=supplier_headers_for(db, other)).status_code == 404
    assert api_client.get(f"/api/birthday/portal/orders/{order.id}").status_code in (401, 403)


def test_supplier_contact_single_number_none_and_unverified(api_client, db):
    sup, _ = _suppliers(db)
    h = supplier_headers_for(db, sup)
    one = _order(db, sup, mobile="+94 77 555 6666", chosen="+94 77 555 6666")
    none = _order(db, sup)
    unverified = _order(db, sup, verified=False, mobile="+94 77 777 8888", chosen="+94 77 777 8888")

    d1 = api_client.get(f"/api/birthday/portal/orders/{one.id}", headers=h).json()
    assert (d1["delivery_contact_phone"], d1["alternative_contact_phone"]) == ("+94 77 555 6666", None)
    d2 = api_client.get(f"/api/birthday/portal/orders/{none.id}", headers=h).json()
    assert (d2["delivery_contact_phone"], d2["alternative_contact_phone"]) == (None, None)
    d3 = api_client.get(f"/api/birthday/portal/orders/{unverified.id}", headers=h).json()
    assert d3["delivery_contact_phone"] is None  # hidden until verified, like the address


# -- Requirement 4: timeline marks HTML email bodies --------------------------

def test_timeline_flags_html_email_and_keeps_messages_as_text(api_client, db, mail):
    from app.core.constants import CommunicationChannel

    _config(db, None)
    sup, _ = _suppliers(db)
    order = _order(db, sup)
    db.add(SupplierCommunication(
        order_id=order.id, supplier_id=sup.id, direction="OUTBOUND", channel=CommunicationChannel.EMAIL.value,
        author_type="SYSTEM", subject="[X] New Birthday Cake Order", body="<!doctype html><html><body><p>Hi</p></body></html>",
        status="SENT", sent_at=datetime.now(UTC),
    ))
    db.commit()
    api_client.post(f"/api/birthday/portal/orders/{order.id}/messages", json={"body": "<b>plain</b> words"},
                    headers=supplier_headers_for(db, sup))
    entries = api_client.get(f"/api/birthday/portal/orders/{order.id}/timeline",
                             headers=supplier_headers_for(db, sup)).json()["entries"]
    email = next(e for e in entries if e["kind"] == "email")
    msg = next(e for e in entries if e["kind"] == "message")
    assert (email["body_format"], email["subject"]) == ("html", "[X] New Birthday Cake Order")
    assert (msg["body_format"], msg["subject"]) == ("text", None)
