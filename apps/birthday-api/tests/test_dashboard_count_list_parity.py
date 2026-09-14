"""Phase 1.6 §4/§21 — the contract this whole cycle exists to enforce:
CARD COUNT == DESTINATION LIST TOTAL, for the exact same predicate, at the
same instant. Every card below is checked by calling the repository's own
count_* method and its corresponding list filter side by side, rather than
hard-coding an expected number — so this test fails the moment the two
predicates ever diverge again, regardless of which one changes.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.repositories.birthday_order_repository import BirthdayOrderRepository
from tests.conftest import headers_for


def _order(db, **overrides):
    from app.models.birthday_order import BirthdayOrder

    defaults = dict(
        order_reference=f"BDAY-EMP{overrides.get('employee_id', 'p')}-2026-00001",
        employee_id="parity-emp",
        employee_number="1",
        employee_name="Parity Person",
        employee_email="parity@example.com",
        birthday_date=date.today() + timedelta(days=10),
        birthday_year=(date.today() + timedelta(days=10)).year,
        office_location="Colombo",
        quantity=1,
        status="PENDING_VERIFICATION",
        address_verification_status="NOT_CHECKED",
    )
    defaults.update(overrides)
    o = BirthdayOrder(**defaults)
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


def test_overdue_delivery_count_matches_due_overdue_list(db):
    repo = BirthdayOrderRepository(db)
    today = date.today()
    _order(db, employee_id="a1", status="CONFIRMED", delivery_date=today - timedelta(days=1))
    _order(db, employee_id="a2", status="COMPLETED", delivery_date=today - timedelta(days=1))  # excluded (terminal)
    _order(db, employee_id="a3", status="PREPARING", delivery_date=today)  # not overdue

    count = repo.count_overdue_delivery(today=today)
    listed = repo.count_filtered(due="overdue")
    assert count == listed == 1


def test_deliveries_today_at_risk_matches_due_today_list(db):
    repo = BirthdayOrderRepository(db)
    today = date.today()
    _order(db, employee_id="b1", status="OUT_FOR_DELIVERY", delivery_date=today)
    _order(db, employee_id="b2", status="CANCELLED", delivery_date=today)  # excluded (terminal)

    count = repo.count_deliveries_today_at_risk(today=today)
    listed = repo.count_filtered(due="today")
    assert count == listed == 1


def test_verification_overdue_count_matches_verify_overdue_list(db):
    repo = BirthdayOrderRepository(db)
    today = date.today()
    _order(db, employee_id="c1", status="PENDING_VERIFICATION", verify_by=today - timedelta(days=1))
    _order(db, employee_id="c2", status="PENDING_VERIFICATION", verify_by=today + timedelta(days=1))  # not overdue yet
    _order(db, employee_id="c3", status="REQUIRES_REVIEW", verify_by=today - timedelta(days=1))  # wrong status

    count = repo.count_verification_overdue(today=today)
    listed = repo.count_filtered(verify="overdue")
    assert count == listed == 1


def test_acceptance_awaiting_and_overdue_match_their_lists(db):
    repo = BirthdayOrderRepository(db)
    now = datetime.now(UTC)
    _order(db, employee_id="d1", status="SENT_TO_SUPPLIER", released_at=now - timedelta(hours=1))
    _order(db, employee_id="d2", status="SENT_TO_SUPPLIER", released_at=now - timedelta(hours=30))
    _order(db, employee_id="d3", status="CONFIRMED", released_at=now - timedelta(hours=30))  # already accepted

    sla_cutoff = now - timedelta(hours=24)
    awaiting_count = repo.count_acceptance_awaiting()
    awaiting_listed = repo.count_filtered(acceptance="awaiting")
    assert awaiting_count == awaiting_listed == 2

    overdue_count = repo.count_acceptance_overdue(sla_cutoff=sla_cutoff)
    overdue_listed = repo.count_filtered(acceptance="overdue", sla_cutoff=sla_cutoff)
    assert overdue_count == overdue_listed == 1


def test_open_issues_count_matches_has_open_issue_list(db, api_client):
    from app.models.order_issue import OrderIssue

    order_with_issue = _order(db, employee_id="e1")
    _order(db, employee_id="e2")
    db.add(OrderIssue(
        order_id=order_with_issue.id, raised_by_type="USER", raised_by_id=1,
        type="OTHER", detail="x", status="OPEN",
    ))
    db.commit()

    headers = headers_for(1, role="BIRTHDAY_USER")
    resp = api_client.get("/api/birthday/orders", params={"has_open_issue": "true"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == order_with_issue.id

    from app.services import attention_service

    assert attention_service.count_open_issues(db) == body["total"]


def test_boundary_exactly_at_sla_cutoff_is_not_yet_overdue(db):
    """A release exactly at the SLA cutoff is not yet overdue — only
    strictly older than the cutoff counts, matching the '<' predicate."""
    repo = BirthdayOrderRepository(db)
    now = datetime.now(UTC)
    cutoff = now - timedelta(hours=24)
    _order(db, employee_id="f1", status="SENT_TO_SUPPLIER", released_at=cutoff)
    assert repo.count_acceptance_overdue(sla_cutoff=cutoff) == 0
    _order(db, employee_id="f2", status="SENT_TO_SUPPLIER", released_at=cutoff - timedelta(seconds=1))
    assert repo.count_acceptance_overdue(sla_cutoff=cutoff) == 1
