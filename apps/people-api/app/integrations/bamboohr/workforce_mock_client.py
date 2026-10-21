"""Realistic in-memory workforce fixture for local/demo/CI use.

Deliberately separate from ``mock_client._ROSTER`` (the Birthday-oriented
fixture) so the Birthday Employee contract's mock population never changes.
Covers the cases workforce consumers must handle: Active and Inactive
employees, a blank Employee Number, a duplicated Employee Number, a
leading-zero Employee Number kept verbatim, and a future starter.
"""

from datetime import date, timedelta

from app.integrations.bamboohr.workforce_client import BambooHRWorkforceClient
from app.integrations.bamboohr.workforce_schemas import BambooHRWorkforceRecord

_NO_TERMINATION = "0000-00-00"  # BambooHR's live sentinel for "not terminated"


def _iso_in_days(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


def _record(
    rid: str, number: str | None, name: str, status: str, *, dept: str = "Internal Bench",
    title: str = "Software Engineer", location: str = "Sri Lanka", hire: str = "2021-03-01",
    term: str = _NO_TERMINATION,
) -> BambooHRWorkforceRecord:
    return BambooHRWorkforceRecord(
        id=rid, employee_number=number, display_name=name, department=dept, job_title=title,
        location=location, employment_status=status, hire_date=hire, termination_date=term,
    )


def _build_roster() -> list[BambooHRWorkforceRecord]:
    return [
        _record("wf-201", "101", "Nimal Perera", "Active", dept="blueAPACHE"),
        _record("wf-202", "102", "Kasun Fernando", "Active", title="QA Engineer"),
        _record("wf-203", "103", "Dilani Silva", "Inactive", hire="2020-06-01", term="2025-08-31"),
        _record("wf-204", None, "Ruwan Jayasinghe", "Active", title="Business Analyst"),  # blank number
        _record("wf-205", "105", "Tharindu Bandara", "Active", dept="Cytrack"),
        _record("wf-206", "105", "Sachini Wickramasinghe", "Active", title="Designer"),  # duplicated number
        _record("wf-207", "0107", "Ishara Gunawardena", "Active", title="Support Engineer"),  # leading zero kept
        _record("wf-208", "108", "Chamara Dissanayake", "Active", hire=_iso_in_days(21)),  # future starter
        _record("wf-209", "109", "Harsha Rathnayake", "Inactive", dept="Cytrack", hire="2019-02-11", term="2024-12-15"),
        _record("wf-210", "110", "Anjali Herath", "Active", location="Brisbane", title="Account Manager"),
    ]


class MockBambooHRWorkforceClient(BambooHRWorkforceClient):
    def list_workforce_records(self) -> list[BambooHRWorkforceRecord]:
        return _build_roster()
