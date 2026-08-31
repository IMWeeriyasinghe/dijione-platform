"""BambooHR integration-layer tests: real-tenant field mapping (using the
exact field names/shapes confirmed by live discovery 2026-08-14, replayed
here as fixtures — no live network call in the automated suite), API
unavailability, missing fields, unexpected status values, and malformed
dates."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.integrations.bamboohr.client import BambooHRFetchError, BambooHRNotConfiguredError
from app.integrations.bamboohr.mapper import map_employee
from app.integrations.bamboohr.schemas import BambooHREmployee


def test_mapper_uses_display_name_over_concatenation():
    employee = BambooHREmployee(
        id="113", first_name="J", last_name="W", display_name="Julia Watson",
        work_email="j@example.com", birth_month=1, birth_day=19,
        department="Dijital Team", office_location="Brisbane", employment_status="Active",
        hire_date="2023-06-01",
    )
    mapped = map_employee(employee)
    assert mapped["full_name"] == "Julia Watson"


def test_mapper_falls_back_to_concatenation_when_display_name_missing():
    employee = BambooHREmployee(
        id="1", first_name="Ann", last_name="Lee", display_name="",
        work_email="a@example.com", birth_month=1, birth_day=1,
        department="X", office_location="Y", employment_status="Active",
    )
    assert map_employee(employee)["full_name"] == "Ann Lee"


def test_mapper_normalizes_termination_sentinel_to_none():
    """BambooHR's real sentinel for "not terminated" is the literal string
    "0000-00-00", not null — confirmed live for 326/484 active records."""
    employee = BambooHREmployee(
        id="1", first_name="A", last_name="B", display_name="A B",
        work_email="a@example.com", birth_month=1, birth_day=1,
        department="X", office_location="Y", employment_status="Active",
        hire_date="2023-06-01", termination_date="0000-00-00",
    )
    assert map_employee(employee)["termination_date"] is None


def test_mapper_parses_real_termination_date():
    employee = BambooHREmployee(
        id="1", first_name="A", last_name="B", display_name="A B",
        work_email="a@example.com", birth_month=1, birth_day=1,
        department="X", office_location="Y", employment_status="Inactive",
        hire_date="2023-06-12", termination_date="2023-10-31",
    )
    mapped = map_employee(employee)
    assert mapped["termination_date"] == date(2023, 10, 31)
    assert mapped["hire_date"] == date(2023, 6, 12)


def test_mapper_handles_malformed_date_gracefully():
    employee = BambooHREmployee(
        id="1", first_name="A", last_name="B", display_name="A B",
        work_email="a@example.com", birth_month=1, birth_day=1,
        department="X", office_location="Y", employment_status="Active",
        hire_date="not-a-date", termination_date="also-not-a-date",
    )
    mapped = map_employee(employee)
    assert mapped["hire_date"] is None
    assert mapped["termination_date"] is None


def test_http_client_not_configured_without_credentials(monkeypatch):
    monkeypatch.setenv("BAMBOOHR_API_KEY", "")
    monkeypatch.setenv("BAMBOOHR_SUBDOMAIN", "")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        from app.integrations.bamboohr.http_client import BambooHRHttpClient

        with pytest.raises(BambooHRNotConfiguredError):
            BambooHRHttpClient()
    finally:
        get_settings.cache_clear()


def test_http_client_wraps_network_failure_as_fetch_error(monkeypatch):
    monkeypatch.setenv("BAMBOOHR_API_KEY", "fake-key-for-test-only")
    monkeypatch.setenv("BAMBOOHR_SUBDOMAIN", "fake-subdomain")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        from app.integrations.bamboohr.http_client import BambooHRHttpClient

        client = BambooHRHttpClient()
        with patch("httpx.post", side_effect=ConnectionError("simulated outage")):
            with pytest.raises(BambooHRFetchError):
                client.list_active_employees()
    finally:
        get_settings.cache_clear()


def test_http_client_maps_real_tenant_shaped_response(monkeypatch):
    """Replays the exact response shape confirmed live 2026-08-14 (field
    names, sentinel values) through the real parsing/mapping code path —
    no network call, just a mocked httpx.post response."""
    monkeypatch.setenv("BAMBOOHR_API_KEY", "fake-key-for-test-only")
    monkeypatch.setenv("BAMBOOHR_SUBDOMAIN", "fake-subdomain")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        from app.integrations.bamboohr.http_client import BambooHRHttpClient

        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.raise_for_status = lambda: None
        fake_response.json.return_value = {
            "employees": [
                {
                    "id": "113", "firstName": "Julia", "lastName": "Watson",
                    "displayName": "Julia Watson", "workEmail": "julia@example.com",
                    "department": "Dijital Team", "location": "Brisbane",
                    "birthday": "01-19", "status": "Active",
                    "hireDate": "2023-06-01", "terminationDate": "0000-00-00",
                },
                {
                    # Inactive employee — must be filtered out server-side.
                    "id": "114", "firstName": "Dana", "lastName": "Fox",
                    "displayName": "Dana Fox", "workEmail": "dana@example.com",
                    "department": "Dijital Team", "location": None,
                    "birthday": "10-02", "status": "Inactive",
                    "hireDate": "2023-06-12", "terminationDate": "2023-10-31",
                },
                {
                    # Unexpected/unknown status value — must be excluded,
                    # not treated as active-by-default.
                    "id": "115", "firstName": "Uncertain", "lastName": "Status",
                    "displayName": "Uncertain Status", "workEmail": "us@example.com",
                    "department": "X", "location": "Y",
                    "birthday": "03-20", "status": "OnLeave",
                    "hireDate": "2020-01-01", "terminationDate": "0000-00-00",
                },
                {
                    # Missing birthday entirely — must be excluded, not crash.
                    "id": "116", "firstName": "No", "lastName": "Birthday",
                    "displayName": "No Birthday", "workEmail": "nb@example.com",
                    "department": "X", "location": "Y",
                    "birthday": None, "status": "Active",
                    "hireDate": "2020-01-01", "terminationDate": "0000-00-00",
                },
            ]
        }

        client = BambooHRHttpClient()
        with patch("httpx.post", return_value=fake_response):
            employees = client.list_active_employees()

        assert [e.id for e in employees] == ["113"]
        assert employees[0].birth_month == 1
        assert employees[0].birth_day == 19
        assert employees[0].hire_date == "2023-06-01"
        assert employees[0].termination_date == "0000-00-00"  # normalized later, in mapper
    finally:
        get_settings.cache_clear()
