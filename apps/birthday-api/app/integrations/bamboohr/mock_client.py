"""Realistic in-memory BambooHR data for local/demo use. Read-only, mirrors
the shape of the real BambooHR employee-directory response it stands in
for (field names verified against a real tenant 2026-08-14 — see
``docs/platform/bamboohr-live-discovery.md``). Birthdays are computed
relative to ``date.today()`` (not hardcoded) so the fixture stays
meaningfully testable regardless of when the tests run — it always has
representatives inside/near the scan window, in the urgent range, one
"late detection" case, and one "future starter" (hired after this
occurrence's birthday) exercising eligibility filtering."""

from datetime import date, timedelta

from app.integrations.bamboohr.client import BambooHRClient
from app.integrations.bamboohr.schemas import BambooHREmployee

_LONG_TENURED_HIRE_DATE = "2019-01-15"  # any past date well before every fixture birthday below


def _in_days(n: int) -> tuple[int, int]:
    """Returns (month, day) for a date ``n`` days from today, so fixtures
    stay relative to "today" instead of hardcoded calendar dates."""
    d = date.today() + timedelta(days=n)
    return d.month, d.day


def _iso_in_days(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


def _build_roster() -> list[BambooHREmployee]:
    m_normal, d_normal = _in_days(9)  # comfortably inside the normal window
    m_short, d_short = _in_days(4)  # short-notice range
    m_urgent, d_urgent = _in_days(1)  # urgent range (0-2 days out)
    m_today, d_today = _in_days(0)  # urgent — today
    m_late, d_late = _in_days(2)  # "new joiner / late detection" — very few days remaining
    m_far, d_far = _in_days(60)  # well outside the scan window
    m_boundary_in, d_boundary_in = _in_days(13)  # just inside a 14-day lookahead
    m_boundary_out, d_boundary_out = _in_days(16)  # just outside a 14-day lookahead
    m_future_starter, d_future_starter = _in_days(5)  # birthday occurs before hire date below

    return [
        BambooHREmployee(
            id="bhr-1001",
            employee_number="101",
            first_name="Amara",
            last_name="Silva",
            display_name="Amara Silva",
            work_email="amara.silva@example.com",
            birth_month=m_normal,
            birth_day=d_normal,
            department="Engineering",
            office_location="Colombo",
            employment_status="Active",
            hire_date=_LONG_TENURED_HIRE_DATE,
        ),
        BambooHREmployee(
            id="bhr-1002",
            employee_number="102",
            first_name="Nadeesha",
            last_name="Perera",
            display_name="Nadeesha Perera",
            work_email="nadeesha.perera@example.com",
            birth_month=m_short,
            birth_day=d_short,
            department="Finance",
            office_location="Colombo",
            employment_status="Active",
            hire_date=_LONG_TENURED_HIRE_DATE,
        ),
        BambooHREmployee(
            id="bhr-1003",
            employee_number="103",
            first_name="Kasun",
            last_name="Fernando",
            display_name="Kasun Fernando",
            work_email="kasun.fernando@example.com",
            birth_month=m_urgent,
            birth_day=d_urgent,
            department="Sales",
            office_location="Kandy",
            employment_status="Active",
            hire_date=_LONG_TENURED_HIRE_DATE,
        ),
        BambooHREmployee(
            id="bhr-1004",
            employee_number="104",
            first_name="Ishara",
            last_name="Gunawardena",
            display_name="Ishara Gunawardena",
            work_email="ishara.gunawardena@example.com",
            birth_month=m_today,
            birth_day=d_today,
            department="Marketing",
            office_location="Kandy",
            employment_status="Active",
            hire_date=_LONG_TENURED_HIRE_DATE,
        ),
        BambooHREmployee(
            id="bhr-1005",
            employee_number=None,  # blank employeeNumber — exercises the missing-number fallback path
            first_name="Ruwan",
            last_name="Jayasuriya",
            display_name="Ruwan Jayasuriya",
            work_email="",  # missing critical data — exercises REQUIRES_ATTENTION path
            birth_month=m_late,
            birth_day=d_late,
            department="Operations",
            office_location="Colombo",
            employment_status="Active",
            hire_date=_LONG_TENURED_HIRE_DATE,
        ),
        BambooHREmployee(
            id="bhr-1006",
            employee_number="106",
            first_name="Tharindu",
            last_name="Bandara",
            display_name="Tharindu Bandara",
            work_email="tharindu.bandara@example.com",
            birth_month=m_late,
            birth_day=d_late,
            department="Engineering",
            office_location="Galle",
            employment_status="Active",
            hire_date=_LONG_TENURED_HIRE_DATE,
        ),
        BambooHREmployee(
            id="bhr-1007",
            employee_number="107",
            first_name="Chamari",
            last_name="Rathnayake",
            display_name="Chamari Rathnayake",
            work_email="chamari.rathnayake@example.com",
            birth_month=m_far,
            birth_day=d_far,
            department="HR",
            office_location="Colombo",
            employment_status="Active",
            hire_date=_LONG_TENURED_HIRE_DATE,
        ),
        BambooHREmployee(
            id="bhr-1008",
            employee_number="108",
            first_name="Dilshan",
            last_name="Wickramasinghe",
            display_name="Dilshan Wickramasinghe",
            work_email="dilshan.wickramasinghe@example.com",
            birth_month=m_boundary_in,
            birth_day=d_boundary_in,
            department="Engineering",
            office_location="Galle",
            employment_status="Active",
            hire_date=_LONG_TENURED_HIRE_DATE,
        ),
        BambooHREmployee(
            id="bhr-1009",
            employee_number="109",
            first_name="Sanduni",
            last_name="Karunaratne",
            display_name="Sanduni Karunaratne",
            work_email="sanduni.karunaratne@example.com",
            birth_month=m_boundary_out,
            birth_day=d_boundary_out,
            department="Sales",
            office_location="Kandy",
            employment_status="Active",
            hire_date=_LONG_TENURED_HIRE_DATE,
        ),
        BambooHREmployee(
            id="bhr-1010",
            employee_number="110",
            first_name="Malith",
            last_name="Abeysekera",
            display_name="Malith Abeysekera",
            work_email="malith.abeysekera@example.com",
            birth_month=m_normal,
            birth_day=d_normal,
            department="Finance",
            office_location="Unassigned Office",  # no matching SupplierLocation — REQUIRES_ATTENTION
            employment_status="Active",
            hire_date=_LONG_TENURED_HIRE_DATE,
        ),
        BambooHREmployee(
            id="bhr-1011",
            employee_number="111",
            first_name="Yasodha",
            last_name="Rajapaksha",
            display_name="Yasodha Rajapaksha",
            work_email="yasodha.rajapaksha@example.com",
            birth_month=m_normal,
            birth_day=d_normal,
            department="Engineering",
            office_location="Colombo",
            employment_status="Terminated",  # excluded by list_active_employees
            hire_date=_LONG_TENURED_HIRE_DATE,
            termination_date=_iso_in_days(-30),
        ),
        BambooHREmployee(
            id="bhr-1012",
            employee_number="112",
            first_name="Nimali",
            last_name="Costa",
            display_name="Nimali Costa",
            work_email="nimali.costa@example.com",
            birth_month=m_future_starter,
            birth_day=d_future_starter,
            department="Engineering",
            office_location="Colombo",
            employment_status="Active",  # mirrors real tenant: Active before start date is possible
            hire_date=_iso_in_days(30),  # hire date is AFTER this occurrence's birthday -> FUTURE_STARTER
        ),
    ]


_ROSTER = _build_roster()


class MockBambooHRClient(BambooHRClient):
    def list_active_employees(self) -> list[BambooHREmployee]:
        return [e for e in _ROSTER if e.employment_status == "Active"]

    def get_employee(self, employee_id: str) -> BambooHREmployee | None:
        return next((e for e in _ROSTER if e.id == employee_id), None)
