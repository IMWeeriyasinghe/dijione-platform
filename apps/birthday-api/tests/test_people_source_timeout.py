"""Phase 1.6 §9/§21 (R1) — the detection-deferral root-cause fix: a
configurable timeout (was hard-coded 5.0s, measured cold start 23s) and
one bounded retry around the daily scan's upfront availability check, so
a transient cold-start miss doesn't defer the whole day's scan by itself.
"""

from __future__ import annotations

import httpx
import pytest

from app.integrations.people_source.client import EmployeeSourceUnavailableError
from app.integrations.people_source.http_adapter import PeopleApiEmployeeSource


class _FlakyOnceClient:
    """Fails the first call, succeeds the second — the exact shape of a
    transient cold-start miss."""

    def __init__(self):
        self.calls = 0

    def list_employees(self, *, active_only: bool = True):
        self.calls += 1
        if self.calls == 1:
            raise httpx.ConnectTimeout("simulated cold-start timeout")
        return [
            {
                "bamboohr_id": "1", "employee_number": "1", "full_name": "Test Person",
                "work_email": "t@example.com", "birth_month": 1, "birth_day": 1,
                "department": "Eng", "office_location": "Colombo",
                "employment_status": "Active", "hire_date": "2020-01-01",
                "termination_date": None, "address_line1": None, "address_line2": None,
                "city": None, "state_province": None, "postal_code": None, "country": None,
            }
        ]


class _AlwaysFailingClient:
    def list_employees(self, *, active_only: bool = True):
        raise httpx.ConnectTimeout("simulated persistent outage")


def _source_with(client) -> PeopleApiEmployeeSource:
    source = PeopleApiEmployeeSource.__new__(PeopleApiEmployeeSource)
    source._client = client  # noqa: SLF001 - test double injection
    return source


def test_retry_absorbs_a_single_transient_cold_start_miss(monkeypatch):
    monkeypatch.setattr("app.integrations.people_source.http_adapter.time.sleep", lambda _s: None)
    source = _source_with(_FlakyOnceClient())
    employees = source.list_active_employees()
    assert len(employees) == 1
    assert employees[0].id == "1"


def test_persistent_outage_still_defers_after_the_one_retry(monkeypatch):
    monkeypatch.setattr("app.integrations.people_source.http_adapter.time.sleep", lambda _s: None)
    source = _source_with(_AlwaysFailingClient())
    with pytest.raises(EmployeeSourceUnavailableError):
        source.list_active_employees()


def test_timeout_is_read_from_settings_not_hard_coded():
    """Regression pin for the actual root cause: the constructor must use
    settings.people_api_timeout_seconds, not a literal 5.0."""
    from app.core.config import get_settings

    settings = get_settings()
    source = PeopleApiEmployeeSource()
    assert source._client._timeout == settings.people_api_timeout_seconds  # noqa: SLF001
