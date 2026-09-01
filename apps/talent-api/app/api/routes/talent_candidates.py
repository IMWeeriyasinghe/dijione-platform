from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import TalentScope, get_talent_scope, require_staff_scope
from app.db.session import get_db
from app.repositories.application_repo import ApplicationRepository
from app.repositories.talent_request_repo import TalentRequestRepository
from app.schemas.candidate import CandidateCreate, CandidateOut, ClientSafeCandidateOut
from app.services.candidate_service import CandidateService

router = APIRouter(prefix="/api/talent", tags=["talent-candidates"])


@router.get("/candidates", response_model=list[CandidateOut])
def list_candidates(
    search: str | None = None,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> list[CandidateOut]:
    service = CandidateService(db)
    candidates = service.repo.list_all(search=search, allowed_client_ids=scope.client_ids)
    return [service.to_out(c, allowed_client_ids=scope.client_ids) for c in candidates]


@router.post("/candidates", response_model=CandidateOut, status_code=status.HTTP_201_CREATED)
def create_candidate(
    payload: CandidateCreate,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> CandidateOut:
    """Retired (DijiTalentFlow real-data completion, 2026-09-02): the
    Candidate master now originates from the Recruitment Source (Lever) —
    see VerifiedPostingPromotionReconciler — not manual entry, so this
    always 403s. The endpoint, CandidateCreate schema, and
    CandidateService.create_candidate are kept, not deleted:
    CandidateService.create_candidate is still exercised directly by
    service-level tests, and a future legitimate non-Lever candidate
    workflow, if one is ever designed, would reuse the same service call.
    """
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "Candidate records originate from the Recruitment Source; they are not created manually.",
    )


@router.get("/candidates/{candidate_id}", response_model=CandidateOut)
def get_candidate(
    candidate_id: int,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> CandidateOut:
    service = CandidateService(db)
    candidate = service.repo.get_by_id(candidate_id)
    if candidate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found")
    out = service.to_out(candidate, allowed_client_ids=scope.client_ids)
    if scope.client_ids is not None and not out.applications:
        # A portfolio-restricted TA with zero in-portfolio applications for
        # this candidate must not learn the candidate exists at all.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found")
    return out


@router.get(
    "/requests/{request_id}/candidates", response_model=list[ClientSafeCandidateOut]
)
def list_request_candidates(
    request_id: int,
    scope: TalentScope = Depends(get_talent_scope),
    db: Session = Depends(get_db),
) -> list[ClientSafeCandidateOut]:
    """Client-safe candidate view scoped to one talent request (CLAUDE.md
    §35). Works for both client and staff personas but a client persona
    only ever sees requests belonging to their own tenant."""
    request = TalentRequestRepository(db).get_by_id(
        request_id, client_id=scope.client_id, allowed_client_ids=scope.client_ids
    )
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Talent request not found")

    application_repo = ApplicationRepository(db)
    service = CandidateService(db)
    applications = application_repo.list_for_request(request_id, client_visible_only=True)
    return [service.to_client_safe_out(app) for app in applications]
