from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import TalentScope, require_staff_scope
from app.api.pagination import (
    TABLE_DEFAULT_PAGE_SIZE,
    TABLE_PAGE_SIZES,
    offset_for,
    require_page_size,
    total_pages,
)
from app.core.constants import ApplicationStatus
from app.db.session import get_db
from app.schemas.application import (
    ApplicationCreate,
    ApplicationOut,
    ApplicationPageOut,
    ApplicationScoreUpdate,
    ApplicationStageUpdate,
    ApplicationStatusUpdate,
    ApplicationVisibilityUpdate,
)
from app.services.application_service import (
    ApplicationNotFoundError,
    ApplicationService,
    CandidateNotFoundError,
    DuplicateApplicationError,
    InvalidApplicationValueError,
    TalentRequestNotFoundError,
)

router = APIRouter(prefix="/api/talent/applications", tags=["talent-applications"])

# DijiTalentFlow is a monitoring/review layer over Lever, not a parallel ATS.
# Recruitment stage and status are Lever facts — they are refreshed from the
# Recruitment Source on every reconcile, so a manual edit here would be
# silently reverted. `score` has no authoritative Lever source at all. All
# three edit endpoints are therefore retired (403), the same way
# `POST /api/talent/requests` and `POST /api/talent/candidates` were. The
# only application field DijiTalentFlow owns and lets a TA change is
# `is_client_visible` — see `update_visibility` below.
_LEVER_OWNED_MSG = (
    "Recruitment stage and status are maintained in Lever and are read-only in "
    "DijiTalentFlow. Candidate scoring is not a DijiTalentFlow capability."
)


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


# Lever carries an offer as the application's *stage* while its status stays
# one of these — so the "Offers in Progress" (?status=OFFER) view includes
# them. Same rule the table previously applied in the browser.
_OFFER_STAGE_STATUSES = (
    ApplicationStatus.ACTIVE.value,
    ApplicationStatus.SHORTLISTED.value,
    ApplicationStatus.CLIENT_REVIEW.value,
)


@router.get("/paged", response_model=ApplicationPageOut)
def list_applications_paged(
    search: str | None = Query(default=None, max_length=200),
    talent_request_id: int | None = None,
    status_filter: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=TABLE_DEFAULT_PAGE_SIZE),
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> ApplicationPageOut:
    """Server-side paginated Applications table (20/50/100, default 20).
    Staff only, portfolio-scoped exactly like ``GET ""``, which is kept
    unchanged for existing consumers (request tab, interview modal)."""
    require_page_size(page_size, TABLE_PAGE_SIZES)
    service = ApplicationService(db)
    rows, total = service.repo.list_page(
        search=search,
        talent_request_id=talent_request_id,
        status=status_filter or None,
        offer_statuses=_OFFER_STAGE_STATUSES,
        allowed_client_ids=scope.client_ids,
        limit=page_size,
        offset=offset_for(page, page_size),
    )
    return ApplicationPageOut(
        items=[service.to_out(a) for a in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages(total, page_size),
    )


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
    except InvalidApplicationValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except CandidateNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found") from exc
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
    """Retired — recruitment stage is a Lever fact (see module docstring).
    The route and schema are kept for contract stability; it always 403s."""
    raise HTTPException(status.HTTP_403_FORBIDDEN, _LEVER_OWNED_MSG)


@router.patch("/{application_id}/status", response_model=ApplicationOut)
def update_status(
    application_id: int,
    payload: ApplicationStatusUpdate,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> ApplicationOut:
    """Retired — recruitment status is a Lever fact (see module docstring)."""
    raise HTTPException(status.HTTP_403_FORBIDDEN, _LEVER_OWNED_MSG)


@router.patch("/{application_id}/score", response_model=ApplicationOut)
def update_score(
    application_id: int,
    payload: ApplicationScoreUpdate,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> ApplicationOut:
    """Retired — candidate scoring has no authoritative source and is not a
    DijiTalentFlow capability (see module docstring)."""
    raise HTTPException(status.HTTP_403_FORBIDDEN, _LEVER_OWNED_MSG)


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
