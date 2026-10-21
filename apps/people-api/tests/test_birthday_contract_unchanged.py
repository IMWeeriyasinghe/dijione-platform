"""Regression guard: the generic Workforce Directory must never change the
Birthday-oriented Employee contract (population, fields, sync runs,
freshness). See docs/platform/workforce-directory.md.
"""

from app.models.employee import Employee
from app.models.sync_run import PeopleSyncRun
from app.services.employee_sync_service import EmployeeSyncService
from app.services.workforce_sync_service import WorkforceDirectoryService
from tests.conftest import internal_headers

_EMPLOYEE_FIELDS = {
    "bamboohr_id", "employee_number", "full_name", "work_email", "birth_month", "birth_day",
    "department", "office_location", "employment_status", "hire_date", "termination_date",
    "address_line1", "address_line2", "city", "state_province", "postal_code", "country", "synced_at",
}


def _employees(api_client):
    resp = api_client.get("/api/people/employees", headers=internal_headers())
    assert resp.status_code == 200
    return resp.json()


def test_employee_contract_population_and_fields_unaffected_by_workforce_sync(api_client, db):
    EmployeeSyncService(db).sync_employees()
    db.commit()
    before = _employees(api_client)
    fresh_before = api_client.get("/api/people/freshness", headers=internal_headers()).json()

    WorkforceDirectoryService(db).reconcile()
    db.commit()
    assert api_client.post(
        "/api/people/internal/workforce-directory/scheduled-sync", headers=internal_headers()
    ).status_code == 202

    after = _employees(api_client)
    assert after == before
    assert len(after) == 11 and all(r["employment_status"] == "Active" for r in after)
    assert set(after[0]) == _EMPLOYEE_FIELDS
    assert api_client.get("/api/people/freshness", headers=internal_headers()).json() == fresh_before


def test_workforce_sync_never_writes_employee_tables(api_client, db):
    assert api_client.post(
        "/api/people/internal/workforce-directory/scheduled-sync", headers=internal_headers()
    ).status_code == 202
    db.expire_all()
    assert db.query(Employee).count() == 0
    assert db.query(PeopleSyncRun).count() == 0
