"""Phase 1.6 §11/§21 — the supplier-portal counterpart of
test_dashboard_count_list_parity.py. Every card must match its own
supplier-scoped list total exactly, and cross-supplier isolation must hold
for every one of them (supplier A's count/list never includes supplier B's
rows)."""

from __future__ import annotations

from datetime import date, timedelta

from app.repositories.birthday_order_repository import BirthdayOrderRepository
from tests.conftest import supplier_headers_for


def _supplier(db, name):
    from app.models.supplier import Supplier

    s = Supplier(name=name, primary_contact_email=f"{name.lower()}@bakery.example.com")
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _order(db, *, supplier, status, employee_id, **overrides):
    from app.models.birthday_order import BirthdayOrder

    defaults = dict(
        order_reference=f"BDAY-EMP{employee_id}-2026-00001",
        employee_id=employee_id,
        employee_name="Supplier Parity Person",
        employee_email="sparity@example.com",
        birthday_date=date.today() + timedelta(days=10),
        birthday_year=(date.today() + timedelta(days=10)).year,
        office_location="Colombo",
        quantity=1,
        status=status,
        supplier_id=supplier.id,
        address_verification_status="VERIFIED",
    )
    defaults.update(overrides)
    o = BirthdayOrder(**defaults)
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


def test_due_today_card_matches_list_and_is_supplier_scoped(api_client, db):
    supplier_a = _supplier(db, "Alpha")
    supplier_b = _supplier(db, "Beta")
    today = date.today()
    _order(db, supplier=supplier_a, status="SENT_TO_SUPPLIER", employee_id="a1", delivery_date=today)
    _order(db, supplier=supplier_b, status="SENT_TO_SUPPLIER", employee_id="b1", delivery_date=today)

    dash = api_client.get("/api/birthday/portal/dashboard", headers=supplier_headers_for(db, supplier_a)).json()
    assert dash["due_today"] == 1

    listed = api_client.get(
        "/api/birthday/portal/orders", params={"due": "today"}, headers=supplier_headers_for(db, supplier_a),
    ).json()
    assert listed["total"] == 1
    assert listed["items"][0]["employee_name"] == "Supplier Parity Person"


def test_open_issues_card_matches_has_open_issue_list(api_client, db):
    from app.models.order_issue import OrderIssue

    supplier_a = _supplier(db, "Gamma")
    order = _order(db, supplier=supplier_a, status="SENT_TO_SUPPLIER", employee_id="g1")
    _order(db, supplier=supplier_a, status="SENT_TO_SUPPLIER", employee_id="g2")
    db.add(OrderIssue(order_id=order.id, raised_by_type="SUPPLIER", raised_by_id=1, type="OTHER", detail="x", status="OPEN"))
    db.commit()

    dash = api_client.get("/api/birthday/portal/dashboard", headers=supplier_headers_for(db, supplier_a)).json()
    assert dash["open_issues"] == 1

    listed = api_client.get(
        "/api/birthday/portal/orders", params={"has_open_issue": "true"}, headers=supplier_headers_for(db, supplier_a),
    ).json()
    assert listed["total"] == 1
    assert listed["items"][0]["order_reference"] == order.order_reference


def test_completed_today_card_matches_completed_today_list_exactly(api_client, db):
    from datetime import datetime, time

    supplier_a = _supplier(db, "Delta")
    # A naive local-midday timestamp on date.today() — avoids the
    # local-vs-UTC calendar-day boundary that a tz-aware datetime.now(UTC)
    # can cross near midnight in a non-UTC dev timezone (unrelated
    # pre-existing sensitivity, not something this test should chase).
    today_completed = _order(
        db, supplier=supplier_a, status="COMPLETED", employee_id="dl1",
        completed_at=datetime.combine(date.today(), time(12, 0)),
    )
    # DELIVERED must NOT be counted or listed — the card is COMPLETED-only,
    # date-bound (the old bug linked to a broader, date-unbound set).
    _order(db, supplier=supplier_a, status="DELIVERED", employee_id="dl2")

    dash = api_client.get("/api/birthday/portal/dashboard", headers=supplier_headers_for(db, supplier_a)).json()
    assert dash["completed_today"] == 1

    listed = api_client.get(
        "/api/birthday/portal/orders", params={"completed": "today"}, headers=supplier_headers_for(db, supplier_a),
    ).json()
    assert listed["total"] == 1
    assert listed["items"][0]["order_reference"] == today_completed.order_reference


def test_cross_supplier_isolation_on_every_card(db):
    repo = BirthdayOrderRepository(db)
    supplier_a = _supplier(db, "Epsilon")
    supplier_b = _supplier(db, "Zeta")
    _order(db, supplier=supplier_a, status="SENT_TO_SUPPLIER", employee_id="e1")
    _order(db, supplier=supplier_b, status="SENT_TO_SUPPLIER", employee_id="z1")

    assert repo.count_for_supplier(supplier_id=supplier_a.id, status_filter="SENT_TO_SUPPLIER") == 1
    assert repo.count_for_supplier(supplier_id=supplier_b.id, status_filter="SENT_TO_SUPPLIER") == 1
