"""Diji On-site module API: metadata, Home-card summary, freshness and the
mirror-sync lifecycle (CLAUDE.md rules 11–18)."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import OnsiteScope, get_onsite_scope, require_internal_service, require_onsite_permission
from app.core.constants import Perm, SyncTriggerType
from app.db.session import get_db
from app.repositories.attendance_repository import AttendanceRepository
from app.services.freshness_service import freshness
from app.services.mirror_sync_service import MirrorSyncService, run_dto

router = APIRouter(prefix="/api/onsite", tags=["onsite"])


def _accepted(run, started: bool) -> dict:
    return {"run_id": run.run_id, "status": run.status, "started": started,
            "message": "Sync started" if started else "A sync is already running"}


@router.get("/metadata")
def metadata() -> dict:
    return {"key": "onsite", "name": "Diji On-site", "description": "On-site Attendance Operations",
            "product_status": "COMING_SOON"}


@router.get("/summary")
def summary(scope: OnsiteScope = Depends(get_onsite_scope), db: Session = Depends(get_db)) -> dict:
    data = freshness(db, allowed_site_ids=scope.allowed_site_ids)
    return {
        "enabled_sites": len(scope.allowed_site_ids),
        "mirrored_events": AttendanceRepository(db).event_count(allowed_site_ids=scope.allowed_site_ids),
        "last_successful_sync_at": data["last_successful_sync_at"],
        "feed_states": {s["site_id"]: s["feed_state"] for s in data["sites"]},
    }


@router.get("/freshness")
def get_freshness(
    site_id: str | None = None,
    scope: OnsiteScope = Depends(require_onsite_permission(Perm.DASHBOARD_READ)),
    db: Session = Depends(get_db),
) -> dict:
    allowed = (scope.require_site(site_id),) if site_id else scope.allowed_site_ids
    return freshness(db, allowed_site_ids=allowed, technical=scope.has(Perm.HEALTH_READ))


@router.post("/sync", status_code=202)
def request_sync(
    background: BackgroundTasks,
    scope: OnsiteScope = Depends(require_onsite_permission(Perm.SYNC_REQUEST)),
    db: Session = Depends(get_db),
) -> dict:
    run, started = MirrorSyncService(db).request_sync(trigger_type=SyncTriggerType.AD_HOC, requested_by_user_id=scope.user.id)
    if started:
        background.add_task(MirrorSyncService.execute_run, run.run_id)
    return _accepted(run, started)


@router.get("/sync/runs/{run_id}")
def get_run(run_id: str, _scope: OnsiteScope = Depends(require_onsite_permission(Perm.HEALTH_READ)),
            db: Session = Depends(get_db)) -> dict:
    run = MirrorSyncService(db).get(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sync run not found")
    return run_dto(run)


@router.get("/sync/history")
def sync_history(limit: int = Query(20, ge=1), _scope: OnsiteScope = Depends(require_onsite_permission(Perm.HEALTH_READ)),
                 db: Session = Depends(get_db)) -> list[dict]:
    return [run_dto(r) for r in MirrorSyncService(db).history(limit=min(limit, 50))]


@router.post("/internal/scheduled-sync", status_code=202, dependencies=[Depends(require_internal_service)])
def scheduled_sync(background: BackgroundTasks, db: Session = Depends(get_db)) -> dict:
    run, started = MirrorSyncService(db).request_sync(trigger_type=SyncTriggerType.SCHEDULED)
    if started:
        background.add_task(MirrorSyncService.execute_run, run.run_id)
    return _accepted(run, started)
