"""Email Safety: employee lookup for recipients (People domain, active employees only), same guards as
the rest of the surface (non-production, birthday.config.manage). Selecting an employee only fills the
form: the allowlist entry grants no application access, and an employee who leaves is reported, never
silently widened or changed."""

from __future__ import annotations

import pytest

from app.integrations.people_source.client import EmployeeSourceUnavailableError
from app.integrations.people_source.schemas import EmployeeRecord
from app.services import recipient_employee_search
from tests.conftest import headers_for

URL = "/api/birthday/admin/test-email-recipients"


def _emp(i, name, email, status="Active"):
    return EmployeeRecord(id=str(i), display_name=name, work_email=email, birth_month=1, birth_day=1,
                          department="Ops", office_location="Colombo", employment_status=status)


class _Source:
    def __init__(self, rows=None, down=False):
        self.rows, self.down = rows or [], down

    def list_active_employees(self):
        if self.down:
            raise EmployeeSourceUnavailableError("people-api down")
        return self.rows


@pytest.fixture()
def source(monkeypatch):
    src = _Source([
        _emp(1, "Nina Perera", "Nina.Perera@dijitalteam.com"),
        _emp(2, "Nina Perera", "nina.perera@dijitalteam.com"),  # same person twice: one result
        _emp(3, "Kamal Silva", "kamal@dijitalteam.com"),
        _emp(4, "No Email", ""),
    ])
    monkeypatch.setattr(recipient_employee_search, "get_employee_source", lambda: src)
    return src


ADMIN = headers_for(500, role="BIRTHDAY_ADMIN")


def test_search_by_name_or_email_deduplicated(api_client, db, source):
    resp = api_client.get(f"{URL}/employee-search?q=nina", headers=ADMIN)
    assert resp.status_code == 200
    assert resp.json()["items"] == [{"full_name": "Nina Perera", "email_address": "nina.perera@dijitalteam.com",
                                     "department": "Ops", "already_recipient": False}]
    by_email = api_client.get(f"{URL}/employee-search?q=kamal@", headers=ADMIN).json()["items"]
    assert [e["full_name"] for e in by_email] == ["Kamal Silva"]


def test_existing_recipients_are_flagged(api_client, db, source):
    api_client.post(URL, json={"email_address": "kamal@dijitalteam.com", "display_label": "Kamal"}, headers=ADMIN)
    hit = api_client.get(f"{URL}/employee-search?q=kamal", headers=ADMIN).json()["items"][0]
    assert hit["already_recipient"] is True


def test_short_query_and_directory_outage(api_client, db, source):
    assert api_client.get(f"{URL}/employee-search?q=n", headers=ADMIN).status_code == 422
    source.down = True
    assert api_client.get(f"{URL}/employee-search?q=nina", headers=ADMIN).status_code == 503


def test_same_guards_as_the_rest_of_email_safety(api_client, db, source, monkeypatch):
    user = headers_for(501, role="BIRTHDAY_USER")
    assert api_client.get(f"{URL}/employee-search?q=nina", headers=user).status_code == 403
    assert api_client.get(f"{URL}/employee-matches", headers=user).status_code == 403
    from app.core.config import get_settings

    monkeypatch.setenv("APP_ENV", "prod")
    get_settings.cache_clear()
    try:
        assert api_client.get(f"{URL}/employee-search?q=nina", headers=ADMIN).status_code == 404
    finally:
        monkeypatch.delenv("APP_ENV", raising=False)
        get_settings.cache_clear()


def test_leavers_and_manual_entries_are_reported_never_changed(api_client, db, source):
    api_client.post(URL, json={"email_address": "kamal@dijitalteam.com", "display_label": "Kamal"}, headers=ADMIN)
    api_client.post(URL, json={"email_address": "supplier.test@example.com", "display_label": "Manual",
                               "recipient_type": "TEST_SUPPLIER"}, headers=ADMIN)
    source.rows = [r for r in source.rows if r.work_email != "kamal@dijitalteam.com"]  # Kamal leaves
    body = api_client.get(f"{URL}/employee-matches", headers=ADMIN).json()
    assert body == {"available": True, "matches": {"kamal@dijitalteam.com": "NOT_AN_ACTIVE_EMPLOYEE",
                                                   "supplier.test@example.com": "NOT_AN_ACTIVE_EMPLOYEE"}}
    listed = api_client.get(URL, headers=ADMIN).json()["items"]
    assert all(r["is_active"] for r in listed)  # nothing changed automatically
    source.down = True
    assert api_client.get(f"{URL}/employee-matches", headers=ADMIN).json() == {"available": False, "matches": {}}
