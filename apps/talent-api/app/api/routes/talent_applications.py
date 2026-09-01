from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import TalentScope, require_staff_scope
from app.db.session import get_db
from app.schemas.application import (
    ApplicationCreate,
    ApplicationOut,
    ApplicationScoreUpdate,
    ApplicationStageUpdate,
    ApplicationStatusUpdate,
    ApplicationVisibilityUpdate,
)
from app.services.application_service import (
    ApplicationNotFoundError,
    ApplicationService,
    DuplicateApplicationError,
    InvalidApplicationValueError,
    TalentRequestNotFoundError,
)

router = APIRouter(prefix="/api/talent/applications", tags=["talent-applications"])


@router.get("", response_model=list[ApplicationOut])
def list_applications(
    search: str | None = None,
    talent_request_id: int | None = None,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> list[ApplicationOut]:
    service = ApplicationService(db)
    applications = service.repo.list_for_scope(
        client_id=None,
        search=search,
        talent_request_id=talent_request_id,
        allowed_client_ids=scope.client_ids,
    )
    return [service.to_out(a) for a in applications]


@router.post("", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
def create_application(
    payload: ApplicationCreate,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> ApplicationOut:
    service = ApplicationService(db)
    try:
        application = service.create_application(
            actor_id=scope.user.id, payload=payload, allowed_client_ids=scope.client_ids
        )
    except DuplicateApplicationError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except TalentRequestNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Talent request not found") from exc
    db.commit()
    db.refresh(application)
    return service.to_out(application)


@router.patch("/{application_id}/stage", response_model=ApplicationOut)
def update_stage(
    application_id: int,
    payload: ApplicationStageUpdate,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> ApplicationOut:
    service = ApplicationService(db)
    application = _apply_or_404(
        service, lambda: service.update_stage(
            application_id=application_id, actor_id=scope.user.id, stage=payload.stage,
            allowed_client_ids=scope.client_ids,
        )
    )
    db.commit()
    db.refresh(application)
    return service.to_out(application)


@router.patch("/{application_id}/status", response_model=ApplicationOut)
def update_status(
    application_id: int,
    payload: ApplicationStatusUpdate,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> ApplicationOut:
    service = ApplicationService(db)
    application = _apply_or_404(
        service,
        lambda: service.update_status(
            application_id=application_id,
            actor_id=scope.user.id,
            status=payload.status,
            rejection_reason=payload.rejection_reason,
            allowed_client_ids=scope.client_ids,
        ),
    )
    db.commit()
    db.refresh(application)
    return service.to_out(application)


@router.patch("/{application_id}/score", response_model=ApplicationOut)
def update_score(
    application_id: int,
    payload: ApplicationScoreUpdate,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> ApplicationOut:
    service = ApplicationService(db)
    application = _apply_or_404(
        service,
        lambda: service.update_score(
            application_id=application_id,
            actor_id=scope.user.id,
            score=payload.score,
            recruiter_notes=payload.recruiter_notes,
            allowed_client_ids=scope.client_ids,
        ),
    )
    db.commit()
    db.refresh(application)
    return service.to_out(application)


@router.patch("/{application_id}/visibility", response_model=ApplicationOut)
def update_visibility(
    application_id: int,
    payload: ApplicationVisibilityUpdate,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> ApplicationOut:
    service = ApplicationService(db)
    application = _apply_or_404(
        service,
        lambda: service.update_visibility(
            application_id=application_id,
            actor_id=scope.user.id,
            is_client_visible=payload.is_client_visible,
            client_visible_notes=payload.client_visible_notes,
            allowed_client_ids=scope.client_ids,
        ),
    )
    db.commit()
    db.refresh(application)
    return service.to_out(application)


def _apply_or_404(service: ApplicationService, action):
    try:
        return action()
    except ApplicationNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found") from exc
    except InvalidApplicationValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
