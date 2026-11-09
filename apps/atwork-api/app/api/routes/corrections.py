"""Employee correction requests: always the verified token's own records."""

from auth_client_py import AuthClaims
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_atwork_permission
from app.api.routes.attendance import get_clock
from app.core.constants import PERM_CORRECTIONS_REQUEST_OWN
from app.core.errors import AttendanceError
from app.db.session import get_db
from app.models.corrections import CorrectionRequest
from app.schemas.corrections import CorrectionIn, CorrectionListOut, CorrectionOut
from app.services import notifications
from app.services.attendance_policy import AttendancePolicy, get_policy
from app.services.attendance_service import Clock
from app.services.correction_service import CorrectionService
from app.services.employee_directory import display_name, employee_names, remember_employee

router = APIRouter(prefix="/api/atwork/corrections", tags=["corrections"])
can_request = require_atwork_permission(PERM_CORRECTIONS_REQUEST_OWN)


def get_correction_service(
    db: Session = Depends(get_db), policy: AttendancePolicy = Depends(get_policy), clock: Clock = Depends(get_clock)
) -> CorrectionService:
    return CorrectionService(db, policy, clock)


def correction_out(item: CorrectionRequest, names: dict, *, can_decide: bool = False) -> CorrectionOut:
    return CorrectionOut(
        id=item.id,
        platform_user_id=item.platform_user_id,
        employee_name=display_name(names, item.platform_user_id),
        kind=item.kind,
        status=item.status,
        session_id=item.session_id,
        reason=item.reason,
        original=item.original,
        proposed=item.proposed,
        reviewer_name=item.reviewer_name,
        reviewed_at=item.reviewed_at,
        decision_note=item.decision_note,
        created_at=item.created_at,
        updated_at=item.updated_at,
        can_decide=can_decide,
    )


@router.get("", response_model=CorrectionListOut)
def list_own(
    status: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    claims: AuthClaims = Depends(can_request),
    db: Session = Depends(get_db),
) -> CorrectionListOut:
    criteria = [CorrectionRequest.platform_user_id == claims.user_id]
    if status:
        criteria.append(CorrectionRequest.status == status)
    total = db.scalar(select(func.count()).select_from(CorrectionRequest).where(*criteria)) or 0
    items = db.scalars(
        select(CorrectionRequest).where(*criteria).order_by(CorrectionRequest.created_at.desc()).limit(limit).offset(offset)
    ).all()
    names = employee_names(db, {claims.user_id})
    return CorrectionListOut(total=total, limit=limit, offset=offset, items=[correction_out(i, names) for i in items])


@router.post("", response_model=CorrectionOut, status_code=201)
def submit(
    body: CorrectionIn,
    background: BackgroundTasks,
    claims: AuthClaims = Depends(can_request),
    db: Session = Depends(get_db),
    service: CorrectionService = Depends(get_correction_service),
) -> CorrectionOut:
    remember_employee(db, claims)
    item, _replayed = service.submit(claims.user_id, body)
    background.add_task(notifications.deliver_after_response)
    return correction_out(item, employee_names(db, {claims.user_id}))


def _own(db: Session, user_id: int, request_id: str) -> CorrectionRequest:
    item = db.get(CorrectionRequest, request_id)
    if item is None or item.platform_user_id != user_id:
        raise AttendanceError("CORRECTION_NOT_FOUND", "Correction request not found.", 404)
    return item


@router.get("/{request_id}", response_model=CorrectionOut)
def detail(request_id: str, claims: AuthClaims = Depends(can_request), db: Session = Depends(get_db)) -> CorrectionOut:
    return correction_out(_own(db, claims.user_id, request_id), employee_names(db, {claims.user_id}))


@router.post("/{request_id}/withdraw", response_model=CorrectionOut)
def withdraw(
    request_id: str,
    background: BackgroundTasks,
    claims: AuthClaims = Depends(can_request),
    db: Session = Depends(get_db),
    service: CorrectionService = Depends(get_correction_service),
) -> CorrectionOut:
    item = service.withdraw(request_id, claims.user_id)
    background.add_task(notifications.deliver_after_response)
    return correction_out(item, employee_names(db, {claims.user_id}))
