"""Team-member delivery contacts: BambooHR mobilePhone (primary) and
homePhone (backup) flow through People API to its consumers."""

from unittest.mock import MagicMock, patch

from app.services.employee_sync_service import EmployeeSyncService
from tests.conftest import internal_headers


def _row(**extra):
    base = {
        "id": "200", "firstName": "Ann", "lastName": "Lee", "displayName": "Ann Lee",
        "workEmail": "ann@example.com", "department": "D", "location": "Colombo",
        "birthday": "02-03", "status": "Active", "hireDate": "2020-01-01",
        "terminationDate": "0000-00-00",
    }
    base.update(extra)
    return base


def test_http_client_requests_and_maps_both_contact_fields(monkeypatch):
    monkeypatch.setenv("BAMBOOHR_API_KEY", "fake-key-for-test-only")
    monkeypatch.setenv("BAMBOOHR_SUBDOMAIN", "fake-subdomain")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        from app.integrations.bamboohr.http_client import BambooHRHttpClient

        resp = MagicMock(status_code=200, raise_for_status=lambda: None)
        resp.json.return_value = {"employees": [
            _row(mobilePhone=" +94 77 123 4567 ", homePhone="+94 11 765 4321"),
            _row(id="201", mobilePhone="+94 77 999 0000", homePhone=""),
        ]}
        with patch("httpx.post", return_value=resp) as post:
            employees = BambooHRHttpClient().list_active_employees()
        fields = post.call_args.kwargs["json"]["fields"]
        assert "mobilePhone" in fields and "homePhone" in fields
        assert (employees[0].mobile_phone, employees[0].home_phone) == ("+94 77 123 4567", "+94 11 765 4321")
        assert (employees[1].mobile_phone, employees[1].home_phone) == ("+94 77 999 0000", None)
    finally:
        get_settings.cache_clear()


def test_sync_persists_and_api_exposes_contacts(api_client, db):
    EmployeeSyncService(db).sync_employees()
    db.commit()
    rows = api_client.get("/api/people/employees", headers=internal_headers()).json()
    by_email = {r["work_email"]: r for r in rows}
    amara = by_email["amara.silva@example.com"]
    assert (amara["mobile_phone"], amara["home_phone"]) == ("+94 77 000 0001", "+94 11 000 0001")
    nadeesha = by_email["nadeesha.perera@example.com"]
    assert (nadeesha["mobile_phone"], nadeesha["home_phone"]) == ("+94 77 000 0002", None)
    assert all("mobile_phone" in r and "home_phone" in r for r in rows)


def _client(monkeypatch):
    monkeypatch.setenv("BAMBOOHR_API_KEY", "fake-key-for-test-only")
    monkeypatch.setenv("BAMBOOHR_SUBDOMAIN", "fake-subdomain")
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.integrations.bamboohr.http_client import BambooHRHttpClient

    return BambooHRHttpClient()


def test_phone_is_read_by_field_id_like_customer_portal(monkeypatch):
    """Regression for the 2026-11-24 report: Customer Portal V2 reads BambooHR
    field id 13 ("Mobile Phone"); a response keyed by id rather than alias must
    still yield the number instead of 'Not in BambooHR'."""
    from app.core.config import get_settings

    try:
        client = _client(monkeypatch)
        resp = MagicMock(status_code=200, raise_for_status=lambda: None)
        resp.json.return_value = {"employees": [
            _row(id="301", **{"13": "+94 77 400 0001", "14": "+94 11 400 0002"}),   # keyed by field id
            _row(id="302", mobilePhone="   ", homePhone=None, **{"13": "+94 77 400 0003"}),  # blank alias, id set
            _row(id="303", mobilePhone="", homePhone=""),                              # genuinely none
        ]}
        with patch("httpx.post", return_value=resp):
            by_id = {e.id: e for e in client.list_active_employees()}
        assert (by_id["301"].mobile_phone, by_id["301"].home_phone) == ("+94 77 400 0001", "+94 11 400 0002")
        assert (by_id["302"].mobile_phone, by_id["302"].home_phone) == ("+94 77 400 0003", None)
        assert (by_id["303"].mobile_phone, by_id["303"].home_phone) == (None, None)
    finally:
        get_settings.cache_clear()


def test_single_employee_lookup_also_carries_phones(monkeypatch):
    """The by-id lookup (terminated employees) previously dropped phone fields."""
    from app.core.config import get_settings

    try:
        client = _client(monkeypatch)
        resp = MagicMock(status_code=200, raise_for_status=lambda: None)
        resp.json.return_value = {"employees": [_row(id="310", mobilePhone="+94 77 500 0001", homePhone="+94 11 500 0002",
                                                     status="Inactive")]}
        with patch("httpx.post", return_value=resp):
            employee = client.get_employee("310")
        assert (employee.mobile_phone, employee.home_phone) == ("+94 77 500 0001", "+94 11 500 0002")
    finally:
        get_settings.cache_clear()
