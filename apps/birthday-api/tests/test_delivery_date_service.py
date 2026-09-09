"""Phase 1 §1.1 — working-day-aware delivery-date defaulting."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services.delivery_date_service import (
    canonicalise_working_days,
    parse_working_days,
    resolve_delivery_date,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, {0, 1, 2, 3, 4}),
        ("", {0, 1, 2, 3, 4}),
        ("   ", {0, 1, 2, 3, 4}),
        ("Mon-Fri", {0, 1, 2, 3, 4}),
        ("Mon,Tue,Wed,Thu,Fri", {0, 1, 2, 3, 4}),
        ("Monday Tuesday", {0, 1}),
        ("Mon-Sat", {0, 1, 2, 3, 4, 5}),
        ("Tue-Sat", {1, 2, 3, 4, 5}),
        ("sun,mon", {6, 0}),
        ("gibberish", {0, 1, 2, 3, 4}),
        ("Fri-Mon", {4, 5, 6, 0}),  # wrap-around range
    ],
)
def test_parse_working_days(raw, expected):
    assert set(parse_working_days(raw)) == expected


def test_canonicalise_working_days():
    assert canonicalise_working_days("mon-fri") == "Mon,Tue,Wed,Thu,Fri"
    assert canonicalise_working_days("") == "Mon,Tue,Wed,Thu,Fri"
    assert canonicalise_working_days("Sat, Sun") == "Sat,Sun"


def _next_weekday(target: int) -> date:
    d = date.today() + timedelta(days=1)
    while d.weekday() != target:
        d += timedelta(days=1)
    return d


def test_weekday_birthday_is_not_shifted():
    wed = _next_weekday(2)
    out, shifted = resolve_delivery_date(wed, "Mon-Fri")
    assert out == wed and shifted is False


def test_saturday_birthday_shifts_to_friday():
    sat = _next_weekday(5)
    out, shifted = resolve_delivery_date(sat, "Mon-Fri")
    assert shifted is True
    assert out == sat - timedelta(days=1)
    assert out.weekday() == 4


def test_sunday_birthday_shifts_to_friday():
    sun = _next_weekday(6)
    out, shifted = resolve_delivery_date(sun, "Mon-Fri")
    assert shifted is True
    assert out.weekday() == 4  # Friday, skipping Saturday


def test_shift_respects_a_saturday_working_supplier():
    sat = _next_weekday(5)
    out, shifted = resolve_delivery_date(sat, "Mon-Sat")
    assert out == sat and shifted is False


def test_detection_shifts_weekend_birthday_and_records_event(db):
    from app.integrations.people_source.mock_adapter import MockEmployeeSource
    from app.integrations.people_source.schemas import EmployeeRecord
    from app.models.birthday_order import BirthdayOrder
    from app.models.detection_config import BirthdayDetectionConfig
    from app.models.order_event import OrderEvent
    from app.models.supplier import Supplier
    from app.services.detection_service import run_daily_scan

    supplier = Supplier(
        name="Weekday Bakery", status="ACTIVE", is_default=True,
        primary_contact_email="wk@bakery.example.com", lead_time_days=3,
        working_days="Mon-Fri",
    )
    db.add(supplier)
    db.commit()

    saturday = _next_weekday(5)

    class _Client(MockEmployeeSource):
        def list_active_employees(self):
            return [
                EmployeeRecord(
                    id="wk-1", employee_number="4001", display_name="Weekend Birthday",
                    work_email="wkb@example.com",
                    birth_month=saturday.month, birth_day=saturday.day,
                    department="Ops", office_location="Colombo",
                    employment_status="Active", hire_date="2019-01-01",
                )
            ]

    config = BirthdayDetectionConfig(
        normal_threshold_days=10, short_notice_threshold_days=5, urgent_threshold_days=2,
        window_lookback_days=1, window_lookahead_days=40,
        default_quantity=1, verify_buffer_days=2, acknowledgement_sla_hours=24,
        auto_release_enabled=True,
    )
    run_daily_scan(db, _Client(), config)

    order = db.query(BirthdayOrder).filter_by(employee_id="wk-1").one()
    assert order.birthday_date == saturday
    assert order.delivery_date == saturday - timedelta(days=1)
    assert order.delivery_date.weekday() == 4
    events = db.query(OrderEvent).filter_by(order_id=order.id, event_type="DELIVERY_DATE_ADJUSTED").all()
    assert len(events) == 1
