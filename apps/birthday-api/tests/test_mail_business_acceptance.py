"""The Birthday-local business-acceptance adapter (order_email_service):
SIMULATED and SUBMITTED both progress the workflow; BLOCKED/DISABLED/FAILED
all record a failure with a distinct last_error and a durably-written
transport_outcome — proving the exact table from the round's approved
correction (mail_client_py stays fully truthful; Birthday decides
business acceptance locally)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from mail_client_py import MailOutcome, MailResult


def _order(db, *, supplier_contact_email="orders@supplier.example.com"):
    from app.models.birthday_order import BirthdayOrder
    from app.models.supplier import Supplier

    supplier = Supplier(name="Adapter Test Supplier", primary_contact_email=supplier_contact_email, lead_time_days=2)
    db.add(supplier)
    db.flush()
    order = BirthdayOrder(
        order_reference="BDAY-ADAPT-2026-00001",
        employee_id="adapt-1", employee_name="Adapter Test",
        employee_email="adapter@example.com",
        birthday_date=date.today() + timedelta(days=10),
        birthday_year=(date.today() + timedelta(days=10)).year,
        office_location="Colombo", quantity=1,
        status="PENDING_VERIFICATION", supplier_id=supplier.id,
        address_verification_status="VERIFIED",
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


class _FixedResultClient:
    def __init__(self, result: MailResult):
        self._result = result

    def send(self, *, to, subject, body, correlation_id=None, content_type="Text"):
        return self._result


@pytest.mark.parametrize(
    "outcome,expected_last_error_fragment",
    [
        (MailOutcome.SIMULATED, None),
        (MailOutcome.SUBMITTED, None),
        (MailOutcome.BLOCKED, "blocked by mail policy"),
        (MailOutcome.DISABLED, "mail transport disabled"),
        (MailOutcome.FAILED, "send failed"),
    ],
)
def test_business_acceptance_and_transport_outcome_recorded(db, monkeypatch, outcome, expected_last_error_fragment):
    from app.services import order_email_service

    result = MailResult(correlation_id="corr-x", outcome=outcome, sent=(outcome == MailOutcome.SUBMITTED))
    monkeypatch.setattr(order_email_service, "get_email_client", lambda db=None: _FixedResultClient(result))

    order = _order(db)
    updated = order_email_service.send_order_to_supplier(db, order, actor_id=1)

    comm = updated.communications[0]
    assert comm.transport_outcome == outcome.value

    if outcome in (MailOutcome.SIMULATED, MailOutcome.SUBMITTED):
        assert comm.status == "SENT"
        assert updated.status == "SENT_TO_SUPPLIER"
    else:
        assert comm.status == "FAILED"
        assert updated.status == "REQUIRES_ATTENTION"
        assert expected_last_error_fragment in comm.last_error
