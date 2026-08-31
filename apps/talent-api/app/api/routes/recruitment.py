"""DijiTalentFlow's consumer surface for the Recruitment Source domain.

The browser calls talent-web -> talent-api (here) -> recruitment-api over
the ``RecruitmentSourceClient`` HTTP contract. talent-api never talks to
Lever and holds no Lever credential (Architecture Completion Plan §3).
A recruitment-api outage degrades this surface (stale freshness, a soft
sync error) — it never 500s the TalentFlow workspace, and the fail-closed
client-visibility decision is made entirely from local tables.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import TalentScope, require_internal_service, require_staff_scope
from app.db.session import SessionLocal, get_db
from app.services.audit_service import AuditService
from app.services.recruitment_consumer_service import (
    RecruitmentConsumerService,
    get_recruitment_client,
)

router = APIRouter(prefix="/api/talent/integrations/recruitment", tags=["recruitment-source"])
internal_router = APIRouter(
    prefix="/api/talent/internal/recruitment", tags=["recruitment-source-internal"]
)


@router.get("/freshness")
def freshness(
    scope: TalentScope = Depends(require_staff_scope), db: Session = Depends(get_db)
) -> dict:
    return RecruitmentConsumerService(db).freshness()


@router.get("/sync/latest")
def sync_latest(scope: TalentScope = Depends(require_staff_scope)) -> dict:
    try:
        return get_recruitment_client()._get("/api/recruitment/sync/latest").json()
    except httpx.HTTPError:
        return {"latest_run": None, "available": False}


@router.get("/sync/history")
def sync_history(limit: int = 20, scope: TalentScope = Depends(require_staff_scope)) -> list[dict]:
    try:
        return get_recruitment_client().list_sync_history(limit=min(limit, 50))
    except httpx.HTTPError:
        return []


@router.get("/sync/{run_id}")
def sync_run(run_id: str, scope: TalentScope = Depends(require_staff_scope)) -> dict:
    try:
        return get_recruitment_client().get_sync_run(run_id)
    except httpx.HTTPError:
        return {"run": None, "available": False}


def _reconcile_bg() -> None:
    db = SessionLocal()
    try:
        RecruitmentConsumerService(db).refresh_projection_and_reconcile()
    finally:
        db.close()


@router.post("/sync", status_code=202)
def request_ad_hoc_sync(
    background: BackgroundTasks,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> dict:
    """Authorized ad-hoc reconciliation. Proxies to recruitment-api (async
    202 + run_id) and then refreshes the local projection + DTC trust
    reconciliation in the background."""
    svc = RecruitmentConsumerService(db)
    try:
        result = svc.request_sync(requested_by_user_id=scope.user.id)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Recruitment Source is unavailable — try again shortly"
        ) from exc

    AuditService().log(
        actor_id=scope.user.id,
        action="recruitment.sync_requested",
        entity_type="RecruitmentSyncRun",
        entity_id=0,
        new_state={"trigger": "AD_HOC", "run_id": result.get("run_id")},
    )
    background.add_task(_reconcile_bg)
    return {
        "run_id": result.get("run_id"),
        "status": result.get("status"),
        "started": result.get("started", False),
        "message": result.get("message", ""),
    }


@internal_router.post("/reconcile", status_code=202)
def reconcile(
    background: BackgroundTasks,
    _: None = Depends(require_internal_service),
) -> dict:
    """Called by an external replica-safe scheduler (a Container Apps Job;
    cron/curl locally), offset from the recruitment-api sync Job. Refreshes
    the local posting projection and runs the DTC trust reconciliation."""
    background.add_task(_reconcile_bg)
    return {"status": "accepted"}
