"""Tests for the live-BambooHR-driven "upcoming birthdays" directory view
(``app/services/directory_service.py`` / ``GET
/api/birthday/employees/upcoming-birthdays``) — distinct from the
``BirthdayOrder``-driven ``/api/birthday/upcoming`` endpoint covered in
``test_detection.py``."""

from __future__ import annotations

from datetime import date

import pytest

from app.integrations.people_source.client import EmployeeSourceClient, EmployeeSourceFetchError
from app.integrations.people_source.mock_adapter import MockEmployeeSource
from app.integrations.people_source.schemas import EmployeeRecord
from app.services.directory_service import NOT_CREATED_STATUS, list_upcoming_birthdays
from tests.conftest import headers_for


class _FixedClient(EmployeeSourceClient):
    """Test double returning a caller-supplied roster, so each test can
    control exactly which employees/statuses/birthdays are in play without
    depending on MockEmployeeSource's relative-to-today fixture."""

    def __init__(self, employees: list[EmployeeRecord]):
        self._employees = employees

    def list_active_employees(self) -> list[EmployeeRecord]:
        # Mirrors the real contract: this method itself only returns
        # already-active employees (mock/live implementations filter
        # server-side) — tests exercising exclusion call it with a
        # pre-filtered list, exactly like MockEmployeeSource does.
        return [e for e in self._employees if e.employment_status == "Active"]

    def get_employee(self, employee_id: str) -> EmployeeRecord | None:
        return next((e for e in self._employees if e.id == employee_id), None)


class _FailingClient(EmployeeSourceClient):
    def list_active_employees(self) -> list[EmployeeRecord]:
        raise ConnectionError("simulated BambooHR outage")

    def get_employee(self, employee_id: str) -> EmployeeRecord | None:
        raise ConnectionError("simulated BambooHR outage")


def _employee(**overrides) -> EmployeeRecord:
    defaults = dict(
        id="bhr-1",
        first_name="Amara",
        last_name="Silva",
        display_name="Amara Silva",
        work_email="amara@example.com",
        birth_month=1,
        birth_day=1,
        department="Engineering",
        office_location="Colombo",
        employment_status="Active",
        hire_date="2019-01-01",  # eligible by default (well before every fixture birthday below)
        termination_date=None,
    )
    defaults.update(overrides)
    return EmployeeRecord(**defaults)


def test_active_employee_included(db):
    today = date(2026, 1, 1)
    client = _FixedClient([_employee(birth_month=1, birth_day=5, employment_status="Active")])
    results = list_upcoming_birthdays(db, client, days=30, today=today)
    assert len(results) == 1
    assert results[0].employee_id == "bhr-1"
    assert results[0].cake_order_status == NOT_CREATED_STATUS


def test_inactive_terminated_employee_excluded(db):
    """Server-side filtering: an inactive/terminated employee must never
    reach the response, even if a caller tried to bypass it, since
    ``list_active_employees`` itself is the single filtering point."""
    today = date(2026, 1, 1)
    client = _FixedClient(
        [
            _employee(id="bhr-1", birth_month=1, birth_day=5, employment_status="Active"),
            _employee(id="bhr-2", birth_month=1, birth_day=6, employment_status="Terminated"),
        ]
    )
    results = list_upcoming_birthdays(db, client, days=30, today=today)
    ids = {r.employee_id for r in results}
    assert ids == {"bhr-1"}


def test_days_until_birthday_calculation(db):
    today = date(2026, 1, 1)
    client = _FixedClient([_employee(birth_month=1, birth_day=11)])
    results = list_upcoming_birthdays(db, client, days=30, today=today)
    assert results[0].days_until_birthday == 10
    assert results[0].birthday == "01-11"


def test_year_boundary_birthday_calculation(db):
    """Today is late December; employee's birthday is early January next
    year. days_until_birthday must be a small positive number (rolling
    into next year), never a large "days since last January" figure."""
    today = date(2025, 12, 28)
    client = _FixedClient([_employee(birth_month=1, birth_day=3)])
    results = list_upcoming_birthdays(db, client, days=30, today=today)
    assert len(results) == 1
    assert results[0].days_until_birthday == 6
    assert results[0].birthday == "01-03"


def test_birthday_outside_window_excluded(db):
    today = date(2026, 1, 1)
    client = _FixedClient([_employee(birth_month=6, birth_day=1)])
    results = list_upcoming_birthdays(db, client, days=30, today=today)
    assert results == []


def test_no_birthdays_in_window_returns_empty_list(db):
    today = date(2026, 1, 1)
    client = _FixedClient([])
    results = list_upcoming_birthdays(db, client, days=30, today=today)
    assert results == []


def test_bamboohr_api_failure_raises_fetch_error_and_is_audited(db, platform_calls):
    with pytest.raises(EmployeeSourceFetchError):
        list_upcoming_birthdays(db, _FailingClient(), days=30, today=date(2026, 1, 1))
    events = [c for c in platform_calls["audit_events"] if c.get("action") == "birthday.employee_source_fetch_failed"]
    assert len(events) == 1
    # No PII (employee names/emails) leaked into the audit metadata.
    assert "amara" not in str(events[0]).lower()


def test_malformed_birthday_field_is_skipped_not_fatal(db, platform_calls):
    """One record with a missing/invalid birth_month must not take down the
    whole response — it's skipped and the rest of the roster still comes
    back, with the skip recorded (no PII) for observability."""
    today = date(2026, 1, 1)
    good = _employee(id="bhr-good", birth_month=1, birth_day=5)
    bad = _employee(id="bhr-bad", birth_month=0, birth_day=0)  # invalid calendar date
    client = _FixedClient([good, bad])

    results = list_upcoming_birthdays(db, client, days=30, today=today)

    assert [r.employee_id for r in results] == ["bhr-good"]
    skipped = [c for c in platform_calls["audit_events"] if c.get("action") == "birthday.employee_source_record_skipped"]
    assert len(skipped) == 1


def test_cake_order_status_reflects_existing_order(db):
    """When a BirthdayOrder already exists for (employee_id, occurrence
    year), cake_order_status must report that order's real status rather
    than the "not_created" stub."""
    from app.core.constants import OrderStatus
    from app.models.birthday_order import BirthdayOrder

    today = date(2026, 1, 1)
    order = BirthdayOrder(
        order_reference="BDAY-EMPbhr-1-2026-1",
        employee_id="bhr-1",
        employee_name="Amara Silva",
        employee_email="amara@example.com",
        birthday_date=date(2026, 1, 11),
        birthday_year=2026,
        office_location="Colombo",
        status=OrderStatus.PENDING_VERIFICATION.value,
    )
    db.add(order)
    db.commit()

    client = _FixedClient([_employee(id="bhr-1", birth_month=1, birth_day=11)])
    results = list_upcoming_birthdays(db, client, days=30, today=today)

    assert len(results) == 1
    assert results[0].cake_order_status == OrderStatus.PENDING_VERIFICATION.value


def test_upcoming_birthdays_endpoint_returns_expected_shape(api_client, db):
    resp = api_client.get(
        "/api/birthday/employees/upcoming-birthdays",
        params={"days": 30},
        headers=headers_for(1, role="BIRTHDAY_USER"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["days"] == 30
    assert isinstance(body["birthdays"], list)
    if body["birthdays"]:
        item = body["birthdays"][0]
        assert set(item.keys()) == {
            "employee_id", "employee_number", "display_name", "days_until_birthday",
            "birthday", "department", "location", "city", "state_province",
            "cake_order_status", "order_id", "order_reference", "hire_date",
            "eligible", "eligibility_reason", "address_verification_status",
        }


def test_upcoming_birthdays_endpoint_requires_auth(api_client, db):
    resp = api_client.get("/api/birthday/employees/upcoming-birthdays")
    assert resp.status_code in (401, 403)


def test_future_starter_included_but_marked_ineligible(db):
    """A future starter (hired after this occurrence's birthday) must
    still appear in the list — never silently dropped — but flagged
    ineligible with the FUTURE_STARTER reason, and no order is implied."""
    today = date(2026, 1, 1)
    client = _FixedClient([_employee(birth_month=1, birth_day=5, hire_date="2026-06-01")])
    results = list_upcoming_birthdays(db, client, days=30, today=today)
    assert len(results) == 1
    assert results[0].eligible is False
    assert results[0].eligibility_reason == "FUTURE_STARTER"
    assert results[0].cake_order_status == NOT_CREATED_STATUS


def test_hire_date_equal_to_occurrence_is_eligible(db):
    today = date(2026, 1, 1)
    client = _FixedClient([_employee(birth_month=1, birth_day=11, hire_date="2026-01-11")])
    results = list_upcoming_birthdays(db, client, days=30, today=today)
    assert results[0].eligible is True
    assert results[0].eligibility_reason == "ELIGIBLE"


def test_missing_hire_date_is_ineligible(db):
    today = date(2026, 1, 1)
    client = _FixedClient([_employee(birth_month=1, birth_day=5, hire_date=None)])
    results = list_upcoming_birthdays(db, client, days=30, today=today)
    assert results[0].eligible is False
    assert results[0].eligibility_reason == "MISSING_HIRE_DATE"


def test_mock_client_excludes_terminated_employee():
    """MockEmployeeSource itself is the active-employee filtering point —
    verifies its fixture roster's one Terminated employee never comes back
    from list_active_employees()."""
    employees = MockEmployeeSource().list_active_employees()
    assert all(e.employment_status == "Active" for e in employees)
    assert "bhr-1011" not in {e.id for e in employees}  # Yasodha Rajapaksha — Terminated
