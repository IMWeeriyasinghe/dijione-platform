"""Phase 1 §1.3 — outbound email: automatic backoff retry, retry
exhaustion, duplicate-send guard, post-release change/cancel notification.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from mail_client_py import MailOutcome, MailResult

from tests.conftest import headers_for


class _ToggleClient:
    """Fails while ``ok`` is False, then succeeds. Stands in for the whole
    MailClient (monkeypatched over get_email_client), so returns real
    MailResult values with truthful outcomes."""

    ok = False

    def send(self, *, to, subject, body, correlation_id=None):
        if not self.ok:
            return MailResult(correlation_id="x", outcome=MailOutcome.FAILED, sent=False, error="toggled off")
        return MailResult(correlation_id="ok-msg", outcome=MailOutcome.SUBMITTED, sent=True)


def _order_ready_to_send(db):
    from app.models.birthday_order import BirthdayOrder
    from app.models.supplier import Supplier

    supplier = Supplier(
        name="Retry Bakery", status="ACTIVE", is_default=True,
        primary_contact_email="retry@bakery.example.com", lead_time_days=2,
    )
    db.add(supplier)
    db.flush()
    order = BirthdayOrder(
        order_reference="BDAY-EMP9100-2026-00001",
        employee_id="rb-1", employee_number="9100", employee_name="Retry Person",
        employee_email="rp@example.com",
        birthday_date=datetime.now(UTC).date() + timedelta(days=10),
        birthday_year=(datetime.now(UTC).date() + timedelta(days=10)).year,
        office_location="Colombo", quantity=1,
        status="PENDING_VERIFICATION", supplier_id=supplier.id,
        address_verification_status="VERIFIED",
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def test_transient_failure_is_retried_and_recovers(db, monkeypatch):
    from app.services import order_email_service

    client = _ToggleClient()
    monkeypatch.setattr(order_email_service, "get_email_client", lambda: client)

    order = _order_ready_to_send(db)
    order_email_service.auto_release_order(db, order)
    db.refresh(order)
    # first send failed -> parked in REQUIRES_ATTENTION, retry scheduled, NOT notified yet
    assert order.status == "REQUIRES_ATTENTION"
    from app.models.supplier_communication import SupplierCommunication

    comm = db.query(SupplierCommunication).filter_by(order_id=order.id).one()
    assert comm.status == "FAILED"
    assert comm.next_retry_at is not None

    # sweep with the retry not yet due -> nothing
    res = order_email_service.retry_failed_outbound(db, now=datetime.now(UTC))
    assert res["retried"] == 0

    # provider recovers; sweep after the backoff window
    client.ok = True
    res = order_email_service.retry_failed_outbound(db, now=comm.next_retry_at + timedelta(seconds=1))
    assert res["succeeded"] == 1
    db.refresh(order)
    assert order.status == "SENT_TO_SUPPLIER"
    db.refresh(comm)
    assert comm.status == "SENT"
    assert comm.next_retry_at is None


def test_retry_exhaustion_notifies_and_records_event(db, monkeypatch):
    from app.models.order_event import OrderEvent
    from app.models.supplier_communication import SupplierCommunication
    from app.services import order_email_service

    calls: list = []
    from app.services.notification_service import NotificationService

    monkeypatch.setattr(order_email_service, "get_email_client", lambda: _ToggleClient())  # always fails
    monkeypatch.setattr(
        NotificationService, "notify_module_role",
        lambda self, **kw: calls.append(kw),
    )

    order = _order_ready_to_send(db)
    order_email_service.auto_release_order(db, order)
    comm = db.query(SupplierCommunication).filter_by(order_id=order.id).one()
    comm.max_attempts = 3
    db.commit()

    now = datetime.now(UTC)
    for _ in range(5):
        now = now + timedelta(hours=6)
        order_email_service.retry_failed_outbound(db, now=now)

    db.refresh(comm)
    assert comm.retry_count == 3
    assert comm.next_retry_at is None
    assert comm.status == "FAILED"
    assert any(c["type"] == "birthday.email_failed" for c in calls)
    assert (
        db.query(OrderEvent)
        .filter_by(order_id=order.id, event_type="EMAIL_RETRY_EXHAUSTED")
        .count()
        == 1
    )


def test_duplicate_release_is_a_no_op(db, monkeypatch):
    from app.models.supplier_communication import SupplierCommunication
    from app.services import order_email_service

    client = _ToggleClient()
    client.ok = True
    monkeypatch.setattr(order_email_service, "get_email_client", lambda: client)

    order = _order_ready_to_send(db)
    order_email_service.auto_release_order(db, order)
    db.refresh(order)
    assert order.status == "SENT_TO_SUPPLIER"

    # a second release attempt must not send a second email
    order_email_service.send_order_to_supplier(db, order, actor_id=1)
    sent = db.query(SupplierCommunication).filter_by(
        order_id=order.id, status="SENT",
    ).count()
    assert sent == 1


def test_post_release_change_emails_the_supplier(api_client, db, monkeypatch):
    from app.models.supplier_communication import SupplierCommunication
    from app.services import order_email_service

    client = _ToggleClient()
    client.ok = True
    monkeypatch.setattr(order_email_service, "get_email_client", lambda: client)

    order = _order_ready_to_send(db)
    order_email_service.auto_release_order(db, order)
    db.refresh(order)

    admin = headers_for(800, role="BIRTHDAY_ADMIN")
    api_client.patch(
        f"/api/birthday/orders/{order.id}",
        json={"delivery_date": str(order.birthday_date - timedelta(days=1))},
        headers=admin,
    )
    bodies = [
        c.body for c in db.query(SupplierCommunication).filter_by(order_id=order.id).all()
    ]
    assert any("has been updated" in (b or "") for b in bodies)

    api_client.post(
        f"/api/birthday/orders/{order.id}/cancel", json={"reason": "duplicate"}, headers=admin,
    )
    bodies = [
        c.body for c in db.query(SupplierCommunication).filter_by(order_id=order.id).all()
    ]
    assert any("CANCELLED" in (b or "") for b in bodies)
