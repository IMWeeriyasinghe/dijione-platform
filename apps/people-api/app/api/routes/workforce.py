"""Generic Workforce Directory API (``docs/platform/workforce-directory.md``).
Internal-only (shared internal token). Separate from ``routes/people.py``
(the Birthday-oriented Employee contract), which is unchanged.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_internal_service
from app.core.constants import SyncTriggerType
from app.db.session import get_db
from app.models.workforce import WorkforceDirectoryEntry
from app.schemas.workforce import (
    WorkforceEntryOut,
    WorkforceFreshnessOut,
    WorkforceSyncAcceptedOut,
    WorkforceSyncRequestIn,
    WorkforceSyncRunOut,
)
from app.services.workforce_sync_service import WorkforceDirectoryService, WorkforceSyncService, run_dto

router = APIRouter(
    prefix="/api/people", tags=["workforce-directory"], dependencies=[Depends(require_internal_service)]
)


def _iso(v) -> str | None:
    return v.isoformat() if v else None


def _entry_out(e: WorkforceDirectoryEntry) -> WorkforceEntryOut:
    return WorkforceEntryOut(
        bamboohr_id=e.bamboohr_id, employee_number=e.employee_number, display_name=e.display_name,
        department=e.department, job_title=e.job_title, location=e.location,
        employment_status=e.employment_status, hire_date=_iso(e.hire_date),
        termination_date=_iso(e.termination_date), present_in_source=e.present_in_source,
        synced_at=_iso(e.last_synced_at),
    )


def _accepted(run, started: bool) -> WorkforceSyncAcceptedOut:
    return WorkforceSyncAcceptedOut(
        run_id=run.run_id, status=run.status, started=started,
        message="Sync started" if started else "A sync is already running",
    )


@router.get("/workforce-directory", response_model=list[WorkforceEntryOut])
def list_workforce_directory(
    status: Literal["all", "active", "inactive"] = "all", db: Session = Depends(get_db)
) -> list[WorkforceEntryOut]:
    return [_entry_out(e) for e in WorkforceDirectoryService(db).list_entries(status)]


@router.get("/workforce-directory/freshness", response_model=WorkforceFreshnessOut)
def workforce_freshness(db: Session = Depends(get_db)) -> WorkforceFreshnessOut:
    return WorkforceFreshnessOut(**WorkforceSyncService(db).freshness())


@router.get("/workforce-directory/sync/history", response_model=list[WorkforceSyncRunOut])
def workforce_sync_history(
    limit: int = Query(20, ge=1), db: Session = Depends(get_db)
) -> list[WorkforceSyncRunOut]:
    return [WorkforceSyncRunOut(**run_dto(r)) for r in WorkforceSyncService(db).history(limit=min(limit, 50))]


@router.post("/internal/workforce-directory/sync", status_code=202, response_model=WorkforceSyncAcceptedOut)
def request_workforce_sync(
    payload: WorkforceSyncRequestIn, background: BackgroundTasks, db: Session = Depends(get_db)
) -> WorkforceSyncAcceptedOut:
    run, started = WorkforceSyncService(db).request_sync(
        trigger_type=SyncTriggerType.AD_HOC,
        requested_by_application=payload.requested_by_application,
        requested_by_user_id=payload.requested_by_user_id,
    )
    if started:
        background.add_task(WorkforceSyncService.execute_run, run.run_id)
    return _accepted(run, started)


@router.post(
    "/internal/workforce-directory/scheduled-sync", status_code=202, response_model=WorkforceSyncAcceptedOut
)
def scheduled_workforce_sync(background: BackgroundTasks, db: Session = Depends(get_db)) -> WorkforceSyncAcceptedOut:
    run, started = WorkforceSyncService(db).request_sync(
        trigger_type=SyncTriggerType.SCHEDULED, requested_by_application="scheduler"
    )
    if started:
        background.add_task(WorkforceSyncService.execute_run, run.run_id)
    return _accepted(run, started)
