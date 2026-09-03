"""External client (magic-link) API surface — consumed only by the
``talentflow-portal`` Client Talent Review Workspace, never by internal
``talent-web`` (plan B.5/B.6/B.9).

Every authenticated route depends on ``get_talent_external_scope``, which
re-validates the backing ``MagicLinkGrant`` on every request and resolves
``client_id`` from that row — never from the URL, a query parameter, or the
token claim. A resource id belonging to another client 404s and leaks
nothing. The permission set is the fixed read-only
``EXTERNAL_SESSION_PERMISSIONS`` subset; there is no create/update/admin
route here, and messages/documents are deliberately absent from V1.

``POST /redeem`` is the only unauthenticated route — it exchanges a raw
link token for a short-lived session JWT, rate-limited, with one
indistinguishable 401 for every failure mode.
"""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import ExternalClientScope, require_external_permission
from app.core.rate_limit import redeem_rate_limiter
from app.db.session import get_db
from app.repositories.application_repo import ApplicationRepository
from app.repositories.talent_request_repo import TalentRequestRepository
from app.schemas.candidate import ClientSafeCandidateOut
from app.schemas.dashboard import ClientDashboardOut
from app.schemas.external import RedeemRequest, RedeemResponse
from app.schemas.talent_request import TalentRequestOut
from app.services.candidate_service import CandidateService
from app.services.dashboard_service import DashboardService
from app.services.interview_service import InterviewService
from app.services.magic_link_service import MagicLinkService
from app.services.talent_request_service import TalentRequestService

router = APIRouter(prefix="/api/talent/external", tags=["talent-external"])

_AUTH_FAILED = "This access link is invalid or has expired"


def _source_ip_hash(request: Request) -> str:
    """Coarse, non-reversible tag for the redeem audit trail — never the
    raw IP, never the token."""
    client_host = request.client.host if request.client else "unknown"
    return hashlib.sha256(client_host.encode("utf-8")).hexdigest()[:16]


@router.post("/redeem", response_model=RedeemResponse)
def redeem_access_link(
    payload: RedeemRequest, request: Request, db: Session = Depends(get_db)
) -> RedeemResponse:
    # Per-source-IP + global fixed-window limiter. Near-constant response
    # regardless of hit/miss; a rejected attempt still consumes budget.
    if not redeem_rate_limiter.allow(request.client.host if request.client else "unknown"):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts — please wait and try again"
        )

    service = MagicLinkService(db)
    grant = service.redeem(payload.token, source_ip_hash=_source_ip_hash(request))
    if grant is None:
        # Identical body for unknown / expired / revoked — no existence
        # signal, no client name.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _AUTH_FAILED)

    token, expires_in = service.mint_session_jwt(grant)
    db.commit()
    return RedeemResponse(access_token=token, expires_in=expires_in)


@router.get("/dashboard", response_model=ClientDashboardOut)
def external_dashboard(
    scope: ExternalClientScope = Depends(require_external_permission("talent.dashboard.read_own")),
    db: Session = Depends(get_db),
) -> ClientDashboardOut:
    return DashboardService(db).client_dashboard(scope.client_id)


@router.get("/requests", response_model=list[TalentRequestOut])
def external_list_requests(
    search: str | None = None,
    stage: str | None = None,
    status_filter: str | None = None,
    scope: ExternalClientScope = Depends(require_external_permission("talent.requests.read_own")),
    db: Session = Depends(get_db),
) -> list[TalentRequestOut]:
    service = TalentRequestService(db)
    requests = service.repo.list_for_scope(
        client_id=scope.client_id,
        search=search,
        stage=stage,
        status=status_filter,
        filter_client_id=None,
        allowed_client_ids=None,
    )
    return [service.to_out(r) for r in requests]


@router.get("/requests/{request_id}", response_model=TalentRequestOut)
def external_get_request(
    request_id: int,
    scope: ExternalClientScope = Depends(require_external_permission("talent.requests.read_own")),
    db: Session = Depends(get_db),
) -> TalentRequestOut:
    service = TalentRequestService(db)
    request = service.repo.get_by_id(request_id, client_id=scope.client_id, allowed_client_ids=None)
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Talent request not found")
    return service.to_out(request)


@router.get(
    "/requests/{request_id}/candidates", response_model=list[ClientSafeCandidateOut]
)
def external_list_request_candidates(
    request_id: int,
    scope: ExternalClientScope = Depends(
        require_external_permission("talent.candidates.read_client_safe")
    ),
    db: Session = Depends(get_db),
) -> list[ClientSafeCandidateOut]:
    # Fail closed on two axes: the request must belong to this client
    # (tenant scope) AND only client-visible applications are returned.
    request = TalentRequestRepository(db).get_by_id(
        request_id, client_id=scope.client_id, allowed_client_ids=None
    )
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Talent request not found")

    service = CandidateService(db)
    applications = ApplicationRepository(db).list_for_request(request_id, client_visible_only=True)
    return [service.to_client_safe_out(app) for app in applications]


@router.get("/applications/{application_id}", response_model=ClientSafeCandidateOut)
def external_get_candidate_review(
    application_id: int,
    scope: ExternalClientScope = Depends(
        require_external_permission("talent.candidates.read_client_safe")
    ),
    db: Session = Depends(get_db),
) -> ClientSafeCandidateOut:
    """Candidate Review Detail — the client-safe single-candidate view
    behind a clickable card on the external request-detail page.

    Fail-closed 4-part invariant, all server-resolved, none from the URL:
    (1) a valid external session (``require_external_permission``);
    (2) ``scope.client_id`` resolved from the re-validated grant row, never
        the URL/query/token claim; (3) the application's own request must
        belong to that exact client — enforced by the join inside
        ``ApplicationRepository.get_by_id(client_id=...)``, the same
        primitive ``external_list_requests``/``external_get_request`` use;
        (4) ``is_client_visible`` must be True. Any failure is an identical
        404 — no existence leak between "wrong client", "not yet curated",
        and "no such application"."""
    application = ApplicationRepository(db).get_by_id(application_id, client_id=scope.client_id)
    if application is None or not application.is_client_visible:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found")

    return CandidateService(db).to_client_safe_out(application)


@router.get("/interviews")
def external_list_interviews(
    scope: ExternalClientScope = Depends(require_external_permission("talent.interviews.read_own")),
    db: Session = Depends(get_db),
) -> list[dict]:
    service = InterviewService(db)
    interviews = service.repo.list_for_scope(client_id=scope.client_id, allowed_client_ids=None)
    return [service.to_client_out(i).model_dump(mode="json") for i in interviews]
