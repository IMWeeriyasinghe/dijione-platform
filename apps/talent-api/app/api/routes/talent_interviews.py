from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import TalentScope, get_talent_scope, require_staff_scope
from app.db.session import get_db
from app.schemas.interview import InterviewCreate, InterviewOut, InterviewStatusUpdate
from app.services.interview_service import (
    ApplicationNotFoundError,
    InterviewNotFoundError,
    InterviewService,
    InvalidInterviewValueError,
)

router = APIRouter(prefix="/api/talent/interviews", tags=["talent-interviews"])


@router.get("")
def list_interviews(
    scope: TalentScope = Depends(get_talent_scope), db: Session = Depends(get_db)
) -> list[dict]:
    """Staff see the full cross-client interview manager (CLAUDE.md §45);
    client personas see only their own, client-safe interviews (§36)."""
    service = InterviewService(db)
    interviews = service.repo.list_for_scope(
        client_id=scope.client_id, allowed_client_ids=scope.client_ids
    )
    if scope.is_staff:
        return [service.to_out(i).model_dump(mode="json") for i in interviews]
    return [service.to_client_out(i).model_dump(mode="json") for i in interviews]


@router.post("", response_model=InterviewOut, status_code=status.HTTP_201_CREATED)
def create_interview(
    payload: InterviewCreate,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> InterviewOut:
    service = InterviewService(db)
    try:
        interview = service.create_interview(
            actor_id=scope.user.id, payload=payload, allowed_client_ids=scope.client_ids
        )
    except ApplicationNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found") from exc
    except InvalidInterviewValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(interview)
    return service.to_out(interview)


@router.patch("/{interview_id}/status", response_model=InterviewOut)
def update_status(
    interview_id: int,
    payload: InterviewStatusUpdate,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> InterviewOut:
    service = InterviewService(db)
    try:
        interview = service.update_status(
            interview_id=interview_id, actor_id=scope.user.id, status=payload.status,
            notes=payload.notes, allowed_client_ids=scope.client_ids,
        )
    except InterviewNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview not found") from exc
    except InvalidInterviewValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    db.refresh(interview)
    return service.to_out(interview)
