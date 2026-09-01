from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import (
    TalentScope,
    get_talent_scope,
    require_customer_success_scope,
    require_staff_scope,
)
from app.db.session import get_db
from app.schemas.talent_request import (
    TalentRequestCreate,
    TalentRequestOut,
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
    return [service.to_out(r) for r in requests]


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
    db.commit()
    db.refresh(request)
    return service.to_out(request)
