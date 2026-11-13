from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import (
    TalentScope,
    get_talent_scope,
    require_customer_success_scope,
    require_staff_scope,
)
from app.api.pagination import (
    CARD_DEFAULT_PAGE_SIZE,
    CARD_PAGE_SIZES,
    offset_for,
    require_page_size,
    total_pages,
)
from app.core.constants import TalentRequestLifecycleStatus
from app.db.session import get_db
from app.schemas.talent_request import (
    TalentRequestCreate,
    TalentRequestOut,
    TalentRequestPageOut,
    TalentRequestReviewDecision,
    TalentRequestStageUpdate,
    TalentRequestTaStatusUpdate,
)
from app.services.talent_request_service import (
    InvalidTransitionError,
    TalentRequestNotFoundError,
    TalentRequestService,
)

router = APIRouter(prefix="/api/talent/requests", tags=["talent-requests"])


@router.get("", response_model=list[TalentRequestOut])
def list_requests(
    search: str | None = None,
    stage: str | None = None,
    status_filter: str | None = None,
    client_id: int | None = None,
    scope: TalentScope = Depends(get_talent_scope),
    db: Session = Depends(get_db),
) -> list[TalentRequestOut]:
    """Client users only ever see their own organization's requests
    (CLAUDE.md §33) — enforced by always passing scope.client_id, never a
    client-supplied id, when the caller is a TALENT_CLIENT persona. Staff
    with a restricted client portfolio (CLAUDE.md-extension §22) only ever
    see ``scope.client_ids``, also never client-supplied."""
    service = TalentRequestService(db)
    requests = service.repo.list_for_scope(
        client_id=scope.client_id,
        search=search,
        stage=stage,
        status=status_filter,
        filter_client_id=client_id,
        allowed_client_ids=scope.client_ids,
    )
    if scope.client_id is not None:
        return [service.to_client_out(r) for r in requests]
    return [service.to_out(r) for r in requests]


# "active" is the Operations Dashboard's definition (DashboardService
# .ta_dashboard): APPROVED + IN_PROGRESS. Applied in SQL on the paged
# endpoint so totals and pages stay correct (the legacy list applied it in
# the browser after an unfiltered fetch).
_ACTIVE_PSEUDO_STATUS = "active"
_ACTIVE_LIFECYCLE = [
    TalentRequestLifecycleStatus.APPROVED.value,
    TalentRequestLifecycleStatus.IN_PROGRESS.value,
]


@router.get("/paged", response_model=TalentRequestPageOut)
def list_requests_paged(
    search: str | None = Query(default=None, max_length=200),
    stage: str | None = None,
    status_filter: str | None = None,
    client_id: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=CARD_DEFAULT_PAGE_SIZE),
    scope: TalentScope = Depends(get_talent_scope),
    db: Session = Depends(get_db),
) -> TalentRequestPageOut:
    """Server-side paginated request cards (12/24/48/96, default 12). Same
    tenant rule as ``GET ""``: a client persona is always pinned to
    ``scope.client_id`` (any ``client_id`` parameter is ignored), portfolio
    staff to ``scope.client_ids``. The legacy unpaginated list is kept for
    existing consumers."""
    require_page_size(page_size, CARD_PAGE_SIZES)
    if status_filter == _ACTIVE_PSEUDO_STATUS:
        statuses = _ACTIVE_LIFECYCLE
    else:
        statuses = [status_filter] if status_filter else None
    service = TalentRequestService(db)
    rows, total = service.repo.list_page(
        client_id=scope.client_id,
        search=search,
        stage=stage,
        statuses=statuses,
        filter_client_id=client_id,
        allowed_client_ids=scope.client_ids,
        limit=page_size,
        offset=offset_for(page, page_size),
    )
    return TalentRequestPageOut(
        items=service.to_out_many(rows, client_view=scope.client_id is not None),
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages(total, page_size),
    )


@router.post("", response_model=TalentRequestOut, status_code=status.HTTP_201_CREATED)
def create_request(
    payload: TalentRequestCreate,
    scope: TalentScope = Depends(get_talent_scope),
    db: Session = Depends(get_db),
) -> TalentRequestOut:
    """Retired (DijiTalentFlow real-data local validation, 2026-09-01):
    DijiTalentFlow is not a client intake portal, so no role is granted
    ``talent.requests.create`` any more (see permissions.py) — this always
    403s. The endpoint, ``TalentRequestCreate`` schema, and
    ``TalentRequestService.create_request`` are kept, not deleted:
    TalentRequest remains a real operational entity, and a future
    internal (TA/CS) creation path would reuse this same service call.
    """
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "DijiTalentFlow does not accept client-submitted talent requests. "
        "Talent requests are created through an internal process.",
    )


@router.get("/{request_id}", response_model=TalentRequestOut)
def get_request(
    request_id: int,
    scope: TalentScope = Depends(get_talent_scope),
    db: Session = Depends(get_db),
) -> TalentRequestOut:
    service = TalentRequestService(db)
    request = service.repo.get_by_id(
        request_id, client_id=scope.client_id, allowed_client_ids=scope.client_ids
    )
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Talent request not found")
    if scope.client_id is not None:
        return service.to_client_out(request)
    return service.to_out(request)


@router.post("/{request_id}/review", response_model=TalentRequestOut)
def review_request(
    request_id: int,
    payload: TalentRequestReviewDecision,
    scope: TalentScope = Depends(require_customer_success_scope),
    db: Session = Depends(get_db),
) -> TalentRequestOut:
    service = TalentRequestService(db)
    try:
        request = service.review_request(
            request_id=request_id,
            actor_id=scope.user.id,
            decision=payload.decision,
            reason=payload.reason,
            allowed_client_ids=scope.client_ids,
        )
    except TalentRequestNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Talent request not found") from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(request)
    return service.to_out(request)


@router.post("/{request_id}/stage", response_model=TalentRequestOut)
def update_stage(
    request_id: int,
    payload: TalentRequestStageUpdate,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> TalentRequestOut:
    service = TalentRequestService(db)
    try:
        request = service.update_stage(
            request_id=request_id,
            actor_id=scope.user.id,
            stage=payload.stage,
            client_safe_status_text=payload.client_safe_status_text,
            allowed_client_ids=scope.client_ids,
        )
    except TalentRequestNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Talent request not found") from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(request)
    return service.to_out(request)


@router.post("/{request_id}/ta-status", response_model=TalentRequestOut)
def update_ta_status(
    request_id: int,
    payload: TalentRequestTaStatusUpdate,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> TalentRequestOut:
    service = TalentRequestService(db)
    try:
        request = service.update_ta_status(
            request_id=request_id,
            actor_id=scope.user.id,
            ta_status=payload.ta_status,
            allowed_client_ids=scope.client_ids,
        )
    except TalentRequestNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Talent request not found") from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(request)
    return service.to_out(request)
