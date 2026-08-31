"""DijiTalentFlow's consumer surface for the Recruitment Source (Lever).

The browser calls talent-web -> talent-api (here) -> the bounded
recruitment_source module. It never calls a source service directly.
Lever remains GET-only (CLAUDE.md §60).
"""

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.api.deps import TalentScope, require_internal_service, require_staff_scope
from app.db.session import get_db
from app.recruitment_source.models import SyncTriggerType
from app.recruitment_source.service import SyncService, _run_dto
from app.services.audit_service import AuditService

router = APIRouter(prefix="/api/talent/integrations/recruitment", tags=["recruitment-source"])


@router.get("/freshness")
def freshness(
    scope: TalentScope = Depends(require_staff_scope), db: Session = Depends(get_db)
) -> dict:
    return SyncService(db).freshness()


@router.get("/sync/latest")
def latest_run(
    scope: TalentScope = Depends(require_staff_scope), db: Session = Depends(get_db)
) -> dict:
    run = SyncService(db).latest()
    return {"latest_run": _run_dto(run) if run else None}


@router.get("/sync/history")
def sync_history(
    limit: int = 20,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [_run_dto(r) for r in SyncService(db).history(limit=min(limit, 50))]


@router.get("/sync/{run_id}")
def get_run(
    run_id: str,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> dict:
    run = SyncService(db).get(run_id)
    if run is None:
        return {"run": None}
    return {"run": _run_dto(run)}


@router.post("/sync", status_code=202)
def request_ad_hoc_sync(
    background: BackgroundTasks,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> dict:
    """Ad-hoc reconciliation requested by an authorized TA staff user.
    Async: returns 202 immediately; the run executes in the background.
    Single-flight — an already-active run is returned instead of starting a
    second full Lever reconciliation."""
    svc = SyncService(db)
    run, started = svc.request_sync(
        trigger_type=SyncTriggerType.AD_HOC,
        requested_by_application="talent-flow",
        requested_by_user_id=scope.user.id,
    )
    if started:
        AuditService().log(
            actor_id=scope.user.id,
            action="recruitment.sync_requested",
            entity_type="RecruitmentSyncRun",
            entity_id=run.id,
            new_state={"trigger": "AD_HOC", "run_id": run.run_id},
        )
        background.add_task(SyncService.execute_run, run.run_id)
    return {
        "run_id": run.run_id,
        "status": run.status,
        "started": started,
        "message": "Sync started" if started else "A sync is already running",
    }


# --- internal: external scheduler entrypoint (Azure Container Apps Job / cron) ---

internal_router = APIRouter(
    prefix="/api/talent/internal/recruitment", tags=["recruitment-source-internal"]
)


@internal_router.post("/scheduled-sync", status_code=202)
def scheduled_sync(
    background: BackgroundTasks,
    _: None = Depends(require_internal_service),
    db: Session = Depends(get_db),
) -> dict:
    """Called every 6 hours by an external replica-safe scheduler (a
    Container Apps Job in Azure; a cron/`curl` locally). A scheduled success
    updates freshness silently — no user notification."""
    svc = SyncService(db)
    run, started = svc.request_sync(
        trigger_type=SyncTriggerType.SCHEDULED, requested_by_application="scheduler"
    )
    if started:
        background.add_task(SyncService.execute_run, run.run_id)
    return {"run_id": run.run_id, "status": run.status, "started": started}
