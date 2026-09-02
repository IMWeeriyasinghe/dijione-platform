"""Canonical Recruitment Source API — the contract DijiOne applications
consume instead of talking to Lever. Internal-only (shared internal token);
Lever is GET-only (CLAUDE.md §60).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_internal_service
from app.db.session import get_db
from app.models.sync_run import SyncTriggerType
from app.recruitment_source.dtc import parse_dtc
from app.repositories.candidacy_repo import RecruitmentCandidacyRepository
from app.repositories.posting_repo import PostingRepository
from app.schemas.recruitment import (
    CandidacyOut,
    DtcTagFact,
    FreshnessOut,
    PostingOut,
    SyncAcceptedOut,
    SyncRequestIn,
    SyncRunOut,
)
from app.services.recruitment_sync_service import RecruitmentSyncService, run_dto

router = APIRouter(
    prefix="/api/recruitment",
    tags=["recruitment-source"],
    dependencies=[Depends(require_internal_service)],
)


def _tags(posting) -> list[str]:
    try:
        raw = json.loads(posting.tags or "[]")
        return [t for t in raw if isinstance(t, str)]
    except (ValueError, TypeError):
        return []


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def _posting_out(posting) -> PostingOut:
    tags = _tags(posting)
    parsed = parse_dtc(tags)
    return PostingOut(
        external_id=posting.lever_posting_id,
        title=posting.title,
        state=posting.state,
        team=posting.team,
        department=posting.department,
        location=posting.location,
        confidentiality=posting.confidentiality,
        tags=tags,
        archived=posting.archived,
        dtc_tag=DtcTagFact(
            status=parsed.status.value,
            client_name=parsed.client_name,
            raw_tag=parsed.raw_tag,
            raw_tags=list(parsed.raw_tags),
        ),
        lever_created_at=_iso(posting.lever_created_at),
        lever_updated_at=_iso(posting.lever_updated_at),
        synced_at=_iso(posting.last_synced_at),
    )


@router.get("/postings", response_model=list[PostingOut])
def list_postings(
    include_archived: bool = True, db: Session = Depends(get_db)
) -> list[PostingOut]:
    return [
        _posting_out(p)
        for p in PostingRepository(db).list_all(include_archived=include_archived)
    ]


@router.get("/postings/{external_id}", response_model=PostingOut)
def get_posting(external_id: str, db: Session = Depends(get_db)) -> PostingOut:
    posting = PostingRepository(db).get_by_lever_id(external_id)
    if posting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown posting")
    return _posting_out(posting)


@router.get("/candidacies", response_model=list[CandidacyOut])
def list_candidacies(
    posting_external_id: str | None = Query(default=None),
    limit: int = Query(default=200, le=500),
    db: Session = Depends(get_db),
) -> list[CandidacyOut]:
    posting_repo = PostingRepository(db)
    posting_local_id: int | None = None
    if posting_external_id is not None:
        posting = posting_repo.get_by_lever_id(posting_external_id)
        if posting is None:
            return []
        posting_local_id = posting.id

    rows = RecruitmentCandidacyRepository(db).list(posting_id=posting_local_id, limit=limit)
    out: list[CandidacyOut] = []
    for c in rows:
        if c.posting is None or c.candidate is None:
            # Belt-and-braces: the repo already inner-joins these out, but
            # never let an unprojectable candidacy 500 the consumer.
            continue
        out.append(
            CandidacyOut(
                external_id=c.lever_opportunity_id,
                posting_external_id=c.posting.lever_posting_id,
                candidate_external_id=c.candidate.lever_contact_id,
                candidate_name=c.candidate.full_name,
                candidate_email=c.candidate.email,
                candidate_headline=c.candidate.headline,
                current_stage=c.current_stage,
                status=c.status,
                lever_archive_reason=c.lever_archive_reason,
                synced_at=_iso(c.updated_at),
            )
        )
    return out


@router.get("/freshness", response_model=FreshnessOut)
def freshness(db: Session = Depends(get_db)) -> FreshnessOut:
    return FreshnessOut(**RecruitmentSyncService(db).freshness())


@router.get("/sync/latest")
def sync_latest(db: Session = Depends(get_db)) -> dict:
    run = RecruitmentSyncService(db).latest()
    return {"latest_run": run_dto(run) if run else None}


@router.get("/sync/history", response_model=list[SyncRunOut])
def sync_history(limit: int = Query(default=20, le=50), db: Session = Depends(get_db)) -> list[SyncRunOut]:
    return [SyncRunOut(**run_dto(r)) for r in RecruitmentSyncService(db).history(limit=limit)]


@router.get("/sync/{run_id}")
def sync_run(run_id: str, db: Session = Depends(get_db)) -> dict:
    run = RecruitmentSyncService(db).get(run_id)
    return {"run": run_dto(run) if run else None}


@router.post("/internal/sync", status_code=202, response_model=SyncAcceptedOut)
def request_ad_hoc_sync(
    payload: SyncRequestIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> SyncAcceptedOut:
    """Authenticated ad-hoc reconciliation requested by a consuming
    application backend (which has already checked the human caller's
    staff scope). Async 202 + run_id; single-flight."""
    svc = RecruitmentSyncService(db)
    run, started = svc.request_sync(
        trigger_type=SyncTriggerType.AD_HOC,
        requested_by_application=payload.requested_by_application,
        requested_by_user_id=payload.requested_by_user_id,
    )
    if started:
        background.add_task(RecruitmentSyncService.execute_run, run.run_id)
    return SyncAcceptedOut(
        run_id=run.run_id,
        status=run.status,
        started=started,
        message="Sync started" if started else "A sync is already running",
    )


@router.post("/internal/scheduled-sync", status_code=202, response_model=SyncAcceptedOut)
def scheduled_sync(background: BackgroundTasks, db: Session = Depends(get_db)) -> SyncAcceptedOut:
    """Called every 6 hours by an external replica-safe scheduler (a
    Container Apps Job in Azure; cron/curl locally). Scheduled success is
    silent; scheduled failure surfaces to TA_MANAGER."""
    svc = RecruitmentSyncService(db)
    run, started = svc.request_sync(
        trigger_type=SyncTriggerType.SCHEDULED, requested_by_application="scheduler"
    )
    if started:
        background.add_task(RecruitmentSyncService.execute_run, run.run_id)
    return SyncAcceptedOut(
        run_id=run.run_id, status=run.status, started=started,
        message="Sync started" if started else "A sync is already running",
    )
