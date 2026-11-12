"""Phase 1.5 §E — the "upcoming birthdays" directory view gains: sort by
Birthday (MM-DD) and Cake Order Status, a ``cake_status_filter``, and
order-reference matching in the free-text ``search``.
"""

from __future__ import annotations

from datetime import date

from app.services.directory_service import NOT_CREATED_STATUS, list_upcoming_birthdays
from tests.test_directory_service import _employee, _FixedClient


def _roster():
    return _FixedClient(
        [
            _employee(id="d-1", birth_month=1, birth_day=20),
            _employee(id="d-2", birth_month=1, birth_day=5),
            _employee(id="d-3", birth_month=1, birth_day=12),
        ]
    )


def test_sort_by_birthday_ascending(db):
    today = date(2026, 1, 1)
    results = list_upcoming_birthdays(
        db, _roster(), days=40, today=today, sort_by="birthday", sort_direction="asc"
    )
    assert [r.birthday for r in results] == ["01-05", "01-12", "01-20"]


def test_sort_by_birthday_descending(db):
    today = date(2026, 1, 1)
    results = list_upcoming_birthdays(
        db, _roster(), days=40, today=today, sort_by="birthday", sort_direction="desc"
    )
    assert [r.birthday for r in results] == ["01-20", "01-12", "01-05"]


def test_sort_by_cake_order_status(db):
    from app.core.constants import OrderStatus
    from app.models.birthday_order import BirthdayOrder

    today = date(2026, 1, 1)
    db.add(
        BirthdayOrder(
            order_reference="BDAY-EMPd-2-2026-1",
            employee_id="d-2",
            employee_name="Amara Silva",
            employee_email="amara@example.com",
            birthday_date=date(2026, 1, 5),
            birthday_year=2026,
            office_location="Colombo",
            status=OrderStatus.PENDING_VERIFICATION.value,
        )
    )
    db.commit()

    results = list_upcoming_birthdays(
        db, _roster(), days=40, today=today, sort_by="cake_order_status", sort_direction="asc"
    )
    # "PENDING_VERIFICATION" < "not_created" lexically, so the real order sorts first.
    assert results[0].employee_id == "d-2"
    assert results[0].cake_order_status == OrderStatus.PENDING_VERIFICATION.value


def test_cake_status_filter_excludes_others(db):
    from app.core.constants import OrderStatus
    from app.models.birthday_order import BirthdayOrder

    today = date(2026, 1, 1)
    db.add(
        BirthdayOrder(
            order_reference="BDAY-EMPd-1-2026-1",
            employee_id="d-1",
            employee_name="Amara Silva",
            employee_email="amara@example.com",
            birthday_date=date(2026, 1, 20),
            birthday_year=2026,
            office_location="Colombo",
            status=OrderStatus.PENDING_VERIFICATION.value,
        )
    )
    db.commit()

    only_pending = list_upcoming_birthdays(
        db, _roster(), days=40, today=today, cake_status_filter="PENDING_VERIFICATION"
    )
    assert [r.employee_id for r in only_pending] == ["d-1"]

    only_not_created = list_upcoming_birthdays(
        db, _roster(), days=40, today=today, cake_status_filter=NOT_CREATED_STATUS
    )
    assert {r.employee_id for r in only_not_created} == {"d-2", "d-3"}


def test_search_matches_order_reference(db):
    from app.core.constants import OrderStatus
    from app.models.birthday_order import BirthdayOrder

    today = date(2026, 1, 1)
    db.add(
        BirthdayOrder(
            order_reference="BDAY-EMP777-2026-04242",
            employee_id="d-3",
            employee_name="Amara Silva",
            employee_email="amara@example.com",
            birthday_date=date(2026, 1, 12),
            birthday_year=2026,
            office_location="Colombo",
            status=OrderStatus.PENDING_VERIFICATION.value,
        )
    )
    db.commit()

    results = list_upcoming_birthdays(db, _roster(), days=40, today=today, search="04242")
    assert [r.employee_id for r in results] == ["d-3"]
