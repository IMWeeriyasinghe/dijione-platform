"""Realistic in-memory employee-directory data for local/demo use —
mirrors the same fixture people-api's own BambooHR mock adapter serves,
translated into the DTO shape birthday-api consumes. Birthdays are
computed relative to ``date.today()`` (not hardcoded) so the fixture stays
meaningfully testable regardless of when the tests run — it always has
representatives inside/near the scan window, in the urgent range, one
"late detection" case, and one "future starter" (hired after this
occurrence's birthday) exercising eligibility filtering.
"""

from datetime import date, timedelta

from app.integrations.people_source.client import EmployeeSourceClient
from app.integrations.people_source.schemas import EmployeeRecord

_LONG_TENURED_HIRE_DATE = "2019-01-15"


def _in_days(n: int) -> tuple[int, int]:
    d = date.today() + timedelta(days=n)
    return d.month, d.day


def _iso_in_days(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


def _build_roster() -> list[EmployeeRecord]:
    m_normal, d_normal = _in_days(9)
    m_short, d_short = _in_days(4)
    m_urgent, d_urgent = _in_days(1)
    m_today, d_today = _in_days(0)
    m_late, d_late = _in_days(2)
    m_far, d_far = _in_days(60)
    m_boundary_in, d_boundary_in = _in_days(13)
    m_boundary_out, d_boundary_out = _in_days(16)
    m_future_starter, d_future_starter = _in_days(5)

    return [
        EmployeeRecord(
            id="bhr-1001", employee_number="101", display_name="Amara Silva",
            work_email="amara.silva@example.com", birth_month=m_normal, birth_day=d_normal,
            department="Engineering", office_location="Colombo", employment_status="Active",
            hire_date=_LONG_TENURED_HIRE_DATE,
            address_line1="12 Galle Road", city="Colombo", state_province="Western",
            postal_code="00300", country="Sri Lanka",
        ),
        EmployeeRecord(
            id="bhr-1002", employee_number="102", display_name="Nadeesha Perera",
            work_email="nadeesha.perera@example.com", birth_month=m_short, birth_day=d_short,
            department="Finance", office_location="Colombo", employment_status="Active",
            hire_date=_LONG_TENURED_HIRE_DATE,
        ),
        EmployeeRecord(
            id="bhr-1003", employee_number="103", display_name="Kasun Fernando",
            work_email="kasun.fernando@example.com", birth_month=m_urgent, birth_day=d_urgent,
            department="Sales", office_location="Kandy", employment_status="Active",
            hire_date=_LONG_TENURED_HIRE_DATE,
        ),
        EmployeeRecord(
            id="bhr-1004", employee_number="104", display_name="Ishara Gunawardena",
            work_email="ishara.gunawardena@example.com", birth_month=m_today, birth_day=d_today,
            department="Marketing", office_location="Kandy", employment_status="Active",
            hire_date=_LONG_TENURED_HIRE_DATE,
        ),
        EmployeeRecord(
            id="bhr-1005", employee_number=None, display_name="Ruwan Jayasuriya",
            work_email="",  # missing critical data -> REQUIRES_ATTENTION path
            birth_month=m_late, birth_day=d_late, department="Operations",
            office_location="Colombo", employment_status="Active", hire_date=_LONG_TENURED_HIRE_DATE,
        ),
        EmployeeRecord(
            id="bhr-1006", employee_number="106", display_name="Tharindu Bandara",
            work_email="tharindu.bandara@example.com", birth_month=m_late, birth_day=d_late,
            department="Engineering", office_location="Galle", employment_status="Active",
            hire_date=_LONG_TENURED_HIRE_DATE,
        ),
        EmployeeRecord(
            id="bhr-1007", employee_number="107", display_name="Chamari Rathnayake",
            work_email="chamari.rathnayake@example.com", birth_month=m_far, birth_day=d_far,
            department="HR", office_location="Colombo", employment_status="Active",
            hire_date=_LONG_TENURED_HIRE_DATE,
        ),
        EmployeeRecord(
            id="bhr-1008", employee_number="108", display_name="Dilshan Wickramasinghe",
            work_email="dilshan.wickramasinghe@example.com",
            birth_month=m_boundary_in, birth_day=d_boundary_in, department="Engineering",
            office_location="Galle", employment_status="Active", hire_date=_LONG_TENURED_HIRE_DATE,
        ),
        EmployeeRecord(
            id="bhr-1009", employee_number="109", display_name="Sanduni Karunaratne",
            work_email="sanduni.karunaratne@example.com",
            birth_month=m_boundary_out, birth_day=d_boundary_out, department="Sales",
            office_location="Kandy", employment_status="Active", hire_date=_LONG_TENURED_HIRE_DATE,
        ),
        EmployeeRecord(
            id="bhr-1010", employee_number="110", display_name="Malith Abeysekera",
            work_email="malith.abeysekera@example.com", birth_month=m_normal, birth_day=d_normal,
            department="Finance", office_location="Unassigned Office", employment_status="Active",
            hire_date=_LONG_TENURED_HIRE_DATE,
        ),
        EmployeeRecord(
            id="bhr-1011", employee_number="111", display_name="Yasodha Rajapaksha",
            work_email="yasodha.rajapaksha@example.com", birth_month=m_normal, birth_day=d_normal,
            department="Engineering", office_location="Colombo",
            employment_status="Terminated",  # excluded by list_active_employees
            hire_date=_LONG_TENURED_HIRE_DATE, termination_date=_iso_in_days(-30),
        ),
        EmployeeRecord(
            id="bhr-1012", employee_number="112", display_name="Nimali Costa",
            work_email="nimali.costa@example.com", birth_month=m_future_starter,
            birth_day=d_future_starter, department="Engineering", office_location="Colombo",
            employment_status="Active",  # mirrors real tenant: Active before start date is possible
            hire_date=_iso_in_days(30),  # after this occurrence's birthday -> FUTURE_STARTER
        ),
    ]


_ROSTER = _build_roster()


class MockEmployeeSource(EmployeeSourceClient):
    def list_active_employees(self) -> list[EmployeeRecord]:
        return [e for e in _ROSTER if e.employment_status == "Active"]

    def get_employee(self, employee_id: str) -> EmployeeRecord | None:
        return next((e for e in _ROSTER if e.id == employee_id), None)
