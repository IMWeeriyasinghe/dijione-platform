"""Self-service attendance. The employee is always the verified token's user."""

from datetime import date, datetime, timedelta

from auth_client_py import AuthClaims
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_atwork_permission
from app.core.constants import PERM_ATTENDANCE_READ_OWN, PERM_ATTENDANCE_RECORD_OWN, STATUS_OPEN
from app.core.errors import AttendanceError
from app.db.session import get_db
from app.models.attendance import AttendanceSession
from app.schemas.attendance import (
    ActionIn,
    ActionOut,
    BreakOut,
    CheckInIn,
    DayTotalsOut,
    HistoryOut,
    SessionOut,
    StatusOut,
    TodayOut,
    TotalsOut,
)
from app.services.attendance_policy import AttendancePolicy, get_policy
from app.services.attendance_service import AttendanceService, Clock, open_break, system_clock
from app.services.time_accounting import Totals, session_totals

router = APIRouter(prefix="/api/atwork/attendance", tags=["attendance"])

_MAX_RANGE_DAYS = 366
_DEFAULT_RANGE_DAYS = 30

can_read = require_atwork_permission(PERM_ATTENDANCE_READ_OWN)
can_record = require_atwork_permission(PERM_ATTENDANCE_RECORD_OWN)


def get_clock() -> Clock:
    return system_clock


def get_service(
    db: Session = Depends(get_db),
    policy: AttendancePolicy = Depends(get_policy),
    clock: Clock = Depends(get_clock),
) -> AttendanceService:
    return AttendanceService(db, policy, clock)


def _totals(totals: Totals) -> TotalsOut:
    return TotalsOut(gross_seconds=totals.gross_seconds, break_seconds=totals.break_seconds, net_seconds=totals.net_seconds)


def _session(session: AttendanceSession, now: datetime) -> SessionOut:
    return SessionOut(
        id=session.id,
        work_mode=session.work_mode,
        status=session.status,
        check_in_at=session.check_in_at,
        check_out_at=session.check_out_at,
        time_zone=session.time_zone,
        breaks=[BreakOut(id=b.id, started_at=b.started_at, ended_at=b.ended_at) for b in session.breaks],
        totals=_totals(session_totals(session, now)),
    )


def _state(session: AttendanceSession | None) -> str:
    if session is None or session.status != STATUS_OPEN:
        return "NOT_CHECKED_IN"
    return "ON_BREAK" if open_break(session) else "WORKING"


def _action(service: AttendanceService, result: tuple[AttendanceSession, bool]) -> ActionOut:
    session, replayed = result
    now = service.now()
    return ActionOut(replayed=replayed, state=_state(session), server_time=now, session=_session(session, now))


@router.get("/status", response_model=StatusOut)
def status(claims: AuthClaims = Depends(can_read), service: AttendanceService = Depends(get_service)) -> StatusOut:
    now = service.now()
    session = service.current(claims.user_id)
    return StatusOut(
        state=_state(session),
        server_time=now,
        time_zone=service.policy.business_time_zone,
        session=_session(session, now) if session else None,
    )


@router.post("/check-in", response_model=ActionOut)
def check_in(
    body: CheckInIn, claims: AuthClaims = Depends(can_record), service: AttendanceService = Depends(get_service)
) -> ActionOut:
    return _action(service, service.check_in(claims.user_id, body.work_mode, body.client_request_id))


@router.post("/breaks/start", response_model=ActionOut)
def start_break(
    body: ActionIn, claims: AuthClaims = Depends(can_record), service: AttendanceService = Depends(get_service)
) -> ActionOut:
    return _action(service, service.start_break(claims.user_id, body.client_request_id))


@router.post("/breaks/end", response_model=ActionOut)
def end_break(
    body: ActionIn, claims: AuthClaims = Depends(can_record), service: AttendanceService = Depends(get_service)
) -> ActionOut:
    return _action(service, service.end_break(claims.user_id, body.client_request_id))


@router.post("/check-out", response_model=ActionOut)
def check_out(
    body: ActionIn, claims: AuthClaims = Depends(can_record), service: AttendanceService = Depends(get_service)
) -> ActionOut:
    return _action(service, service.check_out(claims.user_id, body.client_request_id))


@router.get("/today", response_model=TodayOut)
def today(claims: AuthClaims = Depends(can_read), service: AttendanceService = Depends(get_service)) -> TodayOut:
    now = service.now()
    day = service.local_date(now)
    sessions = service.sessions_for_range(claims.user_id, day, day)
    return TodayOut(
        date=day,
        time_zone=service.policy.business_time_zone,
        server_time=now,
        session_count=len(sessions),
        totals=_totals(service.daily(sessions, now).get(day, Totals())),
        sessions=[_session(s, now) for s in sessions],
    )


@router.get("/history", response_model=HistoryOut)
def history(
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    claims: AuthClaims = Depends(can_read),
    service: AttendanceService = Depends(get_service),
) -> HistoryOut:
    now = service.now()
    end = date_to or service.local_date(now)
    start = date_from or end - timedelta(days=_DEFAULT_RANGE_DAYS - 1)
    if start > end:
        raise AttendanceError("INVALID_DATE_RANGE", "The start date must not be after the end date.", 422)
    if (end - start).days >= _MAX_RANGE_DAYS:
        raise AttendanceError("INVALID_DATE_RANGE", f"The date range must not exceed {_MAX_RANGE_DAYS} days.", 422)
    sessions = service.sessions_for_range(claims.user_id, start, end)
    daily = [
        DayTotalsOut(date=day, **_totals(totals).model_dump())
        for day, totals in sorted(service.daily(sessions, now).items())
        if start <= day <= end
    ]
    return HistoryOut(
        date_from=start,
        date_to=end,
        time_zone=service.policy.business_time_zone,
        total=len(sessions),
        limit=limit,
        offset=offset,
        daily_totals=daily,
        sessions=[_session(s, now) for s in sessions[offset : offset + limit]],
    )


@router.get("/sessions/{session_id}", response_model=SessionOut)
def session_detail(
    session_id: str, claims: AuthClaims = Depends(can_read), service: AttendanceService = Depends(get_service)
) -> SessionOut:
    return _session(service.owned_session(claims.user_id, session_id), service.now())
