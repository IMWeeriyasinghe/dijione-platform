"""Mock-mode end-to-end reconciliation: EmployeeSyncService pulls BambooHR's
active-employee roster into the durable Employee read model. No BambooHR
credential, no network (INTEGRATIONS_MODE=mock).
"""

import uuid

from app.models.employee import Employee
from app.models.sync_run import PeopleSyncRun
from app.services.employee_sync_service import EmployeeSyncService
from app.services.people_sync_service import PeopleSyncService


def test_sync_employees_populates_read_model(db):
    result = EmployeeSyncService(db).sync_employees()
    db.commit()

    assert result["created"] == 11  # 11 Active in the mock roster (1 Terminated excluded)
    rows = db.query(Employee).all()
    assert len(rows) == 11
    amara = db.query(Employee).filter_by(bamboohr_id="bhr-1001").one()
    assert amara.full_name == "Amara Silva"
    assert amara.employee_number == "101"
    assert amara.employment_status == "Active"
    assert amara.last_synced_at is not None


def test_sync_is_idempotent_and_updates_existing_rows(db):
    EmployeeSyncService(db).sync_employees()
    db.commit()
    result = EmployeeSyncService(db).sync_employees()
    db.commit()
    assert result["created"] == 0
    assert result["updated"] == 11
    assert db.query(Employee).count() == 11


def _queued_run(db) -> str:
    run_id = str(uuid.uuid4())
    db.add(
        PeopleSyncRun(
            run_id=run_id, provider="BAMBOOHR", trigger_type="AD_HOC",
            requested_by_application="birthday", status="QUEUED",
        )
    )
    db.commit()
    return run_id


def test_execute_run_completes_and_freshness_reflects_it(db):
    run_id = _queued_run(db)
    PeopleSyncService.execute_run(run_id)
    db.expire_all()

    run = db.query(PeopleSyncRun).filter_by(run_id=run_id).one()
    assert run.status == "SUCCEEDED"
    assert run.records_created == 11

    fresh = PeopleSyncService(db).freshness()
    assert fresh["last_successful_sync_at"] is not None
    assert fresh["latest_run"]["status"] == "SUCCEEDED"
