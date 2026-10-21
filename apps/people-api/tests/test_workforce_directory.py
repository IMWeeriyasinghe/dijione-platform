"""Generic Workforce Directory — full roster (Active + Inactive), verbatim
Employee Numbers, authoritative status, never-delete reconciliation,
single-flight 202 sync, minimum-data DTO, internal-token gated.
"""

import pytest

from app.integrations import factory
from app.integrations.bamboohr.workforce_client import BambooHRWorkforceClient, WorkforceSourceFetchError
from app.integrations.bamboohr.workforce_mock_client import MockBambooHRWorkforceClient
from app.models.workforce import WorkforceDirectoryEntry, WorkforceSyncRun
from app.services.workforce_sync_service import WorkforceDirectoryService
from tests.conftest import internal_headers


class _ListClient(BambooHRWorkforceClient):
    def __init__(self, records):
        self._records = records

    def list_workforce_records(self):
        return self._records


class _FailingClient(BambooHRWorkforceClient):
    def list_workforce_records(self):
        raise WorkforceSourceFetchError("provider down")


@pytest.fixture()
def use_client(monkeypatch):
    def _use(client):
        monkeypatch.setattr(factory, "get_bamboohr_workforce_client", lambda: client)
        import app.services.workforce_sync_service as svc

        monkeypatch.setattr(svc, "get_bamboohr_workforce_client", lambda: client)

    return _use


def _rows(db):
    return {e.bamboohr_id: e for e in db.query(WorkforceDirectoryEntry).all()}


def test_endpoints_require_internal_token(api_client, db):
    for path in (
        "/api/people/workforce-directory",
        "/api/people/workforce-directory/freshness",
        "/api/people/workforce-directory/sync/history",
    ):
        assert api_client.get(path).status_code == 401
    assert api_client.post(
        "/api/people/internal/workforce-directory/sync", json={"requested_by_application": "x"}
    ).status_code == 401
    assert api_client.post("/api/people/internal/workforce-directory/scheduled-sync").status_code == 401


def test_reconcile_stores_full_roster_including_inactive(db):
    result = WorkforceDirectoryService(db).reconcile()
    db.commit()

    rows = _rows(db)
    assert result["total"] == len(MockBambooHRWorkforceClient().list_workforce_records()) == len(rows) == 10
    statuses = {r.employment_status for r in rows.values()}
    assert statuses == {"Active", "Inactive"}
    assert rows["wf-203"].termination_date.isoformat() == "2025-08-31"
    assert rows["wf-201"].termination_date is None  # sentinel normalized


def test_employee_numbers_kept_verbatim_blank_and_duplicates_preserved(db):
    WorkforceDirectoryService(db).reconcile()
    db.commit()
    rows = _rows(db)
    assert rows["wf-207"].employee_number == "0107"  # leading zero kept
    assert rows["wf-204"].employee_number is None  # blank
    assert [r.bamboohr_id for r in rows.values() if r.employee_number == "105"] == ["wf-205", "wf-206"]


def test_status_flip_and_absent_records_on_resync(db, use_client):
    base = MockBambooHRWorkforceClient().list_workforce_records()
    WorkforceDirectoryService(db).reconcile()
    db.commit()

    changed = [r.model_copy(update={"employment_status": "Inactive", "termination_date": "2026-10-01"})
               if r.id == "wf-202" else r for r in base if r.id != "wf-210"]
    use_client(_ListClient(changed))
    result = WorkforceDirectoryService(db).reconcile()
    db.commit()

    rows = _rows(db)
    assert result == {"total": 9, "created": 0, "updated": 1, "unchanged": 8, "absent": 1}
    assert rows["wf-202"].employment_status == "Inactive"
    assert rows["wf-210"].present_in_source is False  # never deleted
    assert len(rows) == 10


def test_failed_run_keeps_previous_directory(api_client, db, use_client):
    WorkforceDirectoryService(db).reconcile()
    db.commit()

    use_client(_FailingClient())
    resp = api_client.post(
        "/api/people/internal/workforce-directory/sync",
        json={"requested_by_application": "consumer"}, headers=internal_headers(),
    )
    assert resp.status_code == 202
    db.expire_all()
    run = db.query(WorkforceSyncRun).one()
    assert run.status == "FAILED" and "WorkforceSourceFetchError" in run.error_summary
    assert len(_rows(db)) == 10


def test_ad_hoc_sync_is_202_and_single_flight(api_client, db):
    from app.core.constants import SyncTriggerType
    from app.services.workforce_sync_service import WorkforceSyncService

    queued, started = WorkforceSyncService(db).request_sync(
        trigger_type=SyncTriggerType.AD_HOC, requested_by_application="consumer"
    )
    assert started
    resp = api_client.post(
        "/api/people/internal/workforce-directory/sync",
        json={"requested_by_application": "other"}, headers=internal_headers(),
    )
    assert resp.status_code == 202
    assert resp.json()["run_id"] == queued.run_id and resp.json()["started"] is False


def test_sync_request_requires_caller_identity(api_client, db):
    resp = api_client.post("/api/people/internal/workforce-directory/sync", json={}, headers=internal_headers())
    assert resp.status_code == 422


def test_scheduled_sync_end_to_end_and_freshness(api_client, db):
    resp = api_client.post("/api/people/internal/workforce-directory/scheduled-sync", headers=internal_headers())
    assert resp.status_code == 202 and resp.json()["started"] is True

    fresh = api_client.get("/api/people/workforce-directory/freshness", headers=internal_headers()).json()
    assert fresh["last_successful_sync_at"] is not None
    assert fresh["latest_run"]["status"] == "SUCCEEDED"
    assert fresh["latest_run"]["records_read"] == 10
    assert fresh["latest_run"]["requested_by_application"] == "scheduler"

    hist = api_client.get("/api/people/workforce-directory/sync/history", headers=internal_headers()).json()
    assert len(hist) == 1


def test_list_status_filter_and_minimum_data_dto(api_client, db):
    WorkforceDirectoryService(db).reconcile()
    db.commit()

    all_rows = api_client.get("/api/people/workforce-directory", headers=internal_headers()).json()
    active = api_client.get("/api/people/workforce-directory?status=active", headers=internal_headers()).json()
    inactive = api_client.get("/api/people/workforce-directory?status=inactive", headers=internal_headers()).json()
    assert (len(all_rows), len(active), len(inactive)) == (10, 8, 2)
    assert api_client.get(
        "/api/people/workforce-directory?status=bogus", headers=internal_headers()
    ).status_code == 422

    keys = set(all_rows[0])
    assert keys == {
        "bamboohr_id", "employee_number", "display_name", "department", "job_title", "location",
        "employment_status", "hire_date", "termination_date", "present_in_source", "synced_at",
    }
    forbidden = {"birth_month", "birth_day", "birthday", "work_email", "address_line1", "city", "postal_code"}
    assert not keys & forbidden
