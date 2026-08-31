"""Canonical People / Workforce API — the contract DijiOne applications
consume instead of talking to BambooHR. Internal-only (shared internal
token); BambooHR is never written to.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_internal_service
from app.core.constants import SyncTriggerType
from app.db.session import get_db
from app.models.employee import Employee
from app.repositories.employee_repo import EmployeeRepository
from app.schemas.people import (
    EmployeeOut,
    FreshnessOut,
    SyncAcceptedOut,
    SyncRequestIn,
    SyncRunOut,
)
from app.services.people_sync_service import PeopleSyncService, run_dto

router = APIRouter(
    prefix="/api/people", tags=["people-source"], dependencies=[Depends(require_internal_service)]
)


def _iso(v) -> str | None:
    return v.isoformat() if v else None


def _employee_out(e: Employee) -> EmployeeOut:
    return EmployeeOut(
        bamboohr_id=e.bamboohr_id, employee_number=e.employee_number, full_name=e.full_name,
        work_email=e.work_email, birth_month=e.birth_month, birth_day=e.birth_day,
        department=e.department, office_location=e.office_location,
        employment_status=e.employment_status, hire_date=_iso(e.hire_date),
        termination_date=_iso(e.termination_date), address_line1=e.address_line1,
        address_line2=e.address_line2, city=e.city, state_province=e.state_province,
        postal_code=e.postal_code, country=e.country, synced_at=_iso(e.last_synced_at),
    )


@router.get("/employees", response_model=list[EmployeeOut])
def list_employees(active_only: bool = True, db: Session = Depends(get_db)) -> list[EmployeeOut]:
    repo = EmployeeRepository(db)
    rows = repo.list_active() if active_only else repo.list_all()
    return [_employee_out(e) for e in rows]


@router.get("/employees/{bamboohr_id}", response_model=EmployeeOut)
def get_employee(bamboohr_id: str, db: Session = Depends(get_db)) -> EmployeeOut:
    row = EmployeeRepository(db).get_by_bamboohr_id(bamboohr_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown employee")
    return _employee_out(row)


@router.get("/freshness", response_model=FreshnessOut)
def freshness(db: Session = Depends(get_db)) -> FreshnessOut:
    return FreshnessOut(**PeopleSyncService(db).freshness())


@router.get("/sync/history", response_model=list[SyncRunOut])
def sync_history(limit: int = 20, db: Session = Depends(get_db)) -> list[SyncRunOut]:
    return [SyncRunOut(**run_dto(r)) for r in PeopleSyncService(db).history(limit=min(limit, 50))]


@router.post("/internal/sync", status_code=202, response_model=SyncAcceptedOut)
def request_ad_hoc_sync(
    payload: SyncRequestIn, background: BackgroundTasks, db: Session = Depends(get_db)
) -> SyncAcceptedOut:
    svc = PeopleSyncService(db)
    run, started = svc.request_sync(
        trigger_type=SyncTriggerType.AD_HOC,
        requested_by_application=payload.requested_by_application,
        requested_by_user_id=payload.requested_by_user_id,
    )
    if started:
        background.add_task(PeopleSyncService.execute_run, run.run_id)
    return SyncAcceptedOut(
        run_id=run.run_id, status=run.status, started=started,
        message="Sync started" if started else "A sync is already running",
    )


@router.post("/internal/scheduled-sync", status_code=202, response_model=SyncAcceptedOut)
def scheduled_sync(background: BackgroundTasks, db: Session = Depends(get_db)) -> SyncAcceptedOut:
    svc = PeopleSyncService(db)
    run, started = svc.request_sync(
        trigger_type=SyncTriggerType.SCHEDULED, requested_by_application="scheduler"
    )
    if started:
        background.add_task(PeopleSyncService.execute_run, run.run_id)
    return SyncAcceptedOut(
        run_id=run.run_id, status=run.status, started=started,
        message="Sync started" if started else "A sync is already running",
    )
