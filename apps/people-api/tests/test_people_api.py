"""Canonical People API — internal-token gated; exposes the employee read
model + freshness + the 202 single-flight ad-hoc sync.
"""

from app.services.employee_sync_service import EmployeeSyncService
from tests.conftest import internal_headers


def test_endpoints_require_internal_token(api_client, db):
    for path in ("/api/people/employees", "/api/people/freshness"):
        assert api_client.get(path).status_code == 401
    assert api_client.post("/api/people/internal/sync", json={}).status_code == 401


def test_list_employees_active_only(api_client, db):
    EmployeeSyncService(db).sync_employees()
    db.commit()

    resp = api_client.get("/api/people/employees", headers=internal_headers())
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 11
    assert all(r["employment_status"] == "Active" for r in rows)


def test_get_employee_by_bamboohr_id(api_client, db):
    EmployeeSyncService(db).sync_employees()
    db.commit()
    resp = api_client.get("/api/people/employees/bhr-1001", headers=internal_headers())
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Amara Silva"
    assert api_client.get("/api/people/employees/nope", headers=internal_headers()).status_code == 404


def test_inactive_live_lookup_escape_hatch(api_client, db):
    # bhr-1011 is Terminated in the mock roster -> never in the read model,
    # but the escape hatch does a live (mock) lookup for historical tooling.
    resp = api_client.get(
        "/api/people/employees/bhr-1011",
        params={"include_inactive_live_lookup": True}, headers=internal_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Yasodha Rajapaksha"
    assert resp.json()["employment_status"] == "Terminated"

    # without the flag it's a plain 404 (not in the read model)
    assert api_client.get("/api/people/employees/bhr-1011", headers=internal_headers()).status_code == 404


def test_ad_hoc_sync_is_202_and_single_flight(api_client, db):
    first = api_client.post(
        "/api/people/internal/sync", json={"requested_by_user_id": 3}, headers=internal_headers()
    )
    assert first.status_code == 202
    assert first.json()["started"] is True
    run_id = first.json()["run_id"]

    from app.models.sync_run import PeopleSyncRun

    db.query(PeopleSyncRun).filter_by(run_id=run_id).update({"status": "RUNNING"})
    db.commit()
    second = api_client.post("/api/people/internal/sync", json={}, headers=internal_headers())
    assert second.status_code == 202
    assert second.json()["started"] is False
    assert second.json()["run_id"] == run_id
