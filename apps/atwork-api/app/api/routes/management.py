"""Management APIs: organization-wide visibility, each behind an explicit permission."""

from collections import Counter
from datetime import date, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from auth_client_py import AuthClaims
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.api.deps import require_management_permission
from app.api.routes.attendance import _session, _state, _totals, get_clock
from app.api.routes.corrections import correction_out, get_correction_service
from app.core.constants import (
    CORRECTION_PENDING,
    MODULE_ATWORK,
    PERM_ATTENDANCE_READ,
    PERM_AUDIT_READ,
    PERM_CORRECTIONS_APPROVE,
    PERM_CORRECTIONS_REVIEW,
    PERM_REPORTS_EXPORT,
    PERM_REPORTS_READ,
    PERM_SETTINGS_MANAGE,
    STATUS_COMPLETED,
    STATUS_OPEN,
)
from app.core.errors import AttendanceError
from app.db.base import utcnow
from app.db.session import get_db
from app.models.attendance import AttendanceEvent, AttendanceSession, new_id
from app.models.corrections import AttendanceEmployee, AtworkSettings, CorrectionRequest
from app.schemas.attendance import DayTotalsOut
from app.schemas.corrections import ApproveIn, CorrectionListOut, CorrectionOut, RejectIn
from app.schemas.management import (
    AuditEventOut,
    AuditListOut,
    CorrectionReportOut,
    EmployeeHistoryOut,
    EmployeeListOut,
    EmployeeOut,
    EmployeeSummaryOut,
    LiveEmployeeOut,
    ManagedSessionOut,
    MissedCheckoutOut,
    MissedCheckoutReportOut,
    ModeTotalsOut,
    OverviewOut,
    ReportSummaryOut,
    SettingsIn,
    SettingsOut,
)
from app.services.attendance_policy import AttendancePolicy, get_policy
from app.services.attendance_service import AttendanceService, Clock
from app.services.correction_service import CorrectionService
from app.services.employee_directory import display_name, employee_names
from app.services.reporting import ReportFilter, Reporting, checked_range, stamp, to_csv, to_xlsx
from app.services.time_accounting import daily_totals, local_day_bounds

router = APIRouter(prefix="/api/atwork/management", tags=["management"])

can_read = require_management_permission(PERM_ATTENDANCE_READ)
can_review = require_management_permission(PERM_CORRECTIONS_REVIEW)
can_approve = require_management_permission(PERM_CORRECTIONS_APPROVE)
can_report = require_management_permission(PERM_REPORTS_READ)
can_export = require_management_permission(PERM_REPORTS_EXPORT)
can_manage_settings = require_management_permission(PERM_SETTINGS_MANAGE)
can_audit = require_management_permission(PERM_AUDIT_READ)


def _service(
    db: Session = Depends(get_db), policy: AttendancePolicy = Depends(get_policy), clock: Clock = Depends(get_clock)
) -> AttendanceService:
    return AttendanceService(db, policy, clock)


def _employee(db: Session, user_id: int, names: dict, open_map: dict[int, AttendanceSession]) -> EmployeeOut:
    row = names.get(user_id)
    return EmployeeOut(
        platform_user_id=user_id,
        employee_name=display_name(names, user_id),
        email=row.email if row else None,
        state=_state(open_map.get(user_id)),
    )


def _open_sessions(db: Session, user_ids: set[int] | None = None) -> list[AttendanceSession]:
    stmt = select(AttendanceSession).where(AttendanceSession.status == STATUS_OPEN)
    if user_ids is not None:
        stmt = stmt.where(AttendanceSession.platform_user_id.in_(user_ids))
    return list(db.scalars(stmt.order_by(AttendanceSession.check_in_at)))


@router.get("/overview", response_model=OverviewOut)
def overview(claims: AuthClaims = Depends(can_read), service: AttendanceService = Depends(_service)) -> OverviewOut:
    db, now = service.db, service.now()
    day = service.local_date(now)
    report = Reporting(db, service.policy, now)
    flt = ReportFilter(day, day)
    today = report.sessions(flt)
    live = _open_sessions(db)
    names = employee_names(db, {s.platform_user_id for s in [*today, *live]})
    cutoff = now - timedelta(hours=service.policy.missed_checkout_hours)

    def card(session: AttendanceSession) -> LiveEmployeeOut:
        state = _state(session)
        return LiveEmployeeOut(
            platform_user_id=session.platform_user_id,
            employee_name=display_name(names, session.platform_user_id),
            state=state,
            session=_session(session, now),
            overdue=session.check_in_at <= cutoff,
        )

    cards = [card(s) for s in live]
    completed = [s for s in today if s.status == STATUS_COMPLETED]
    exceptions = [MissedCheckoutOut(**row) for row in report.missed_checkouts()]
    module = claims.module(MODULE_ATWORK)
    pending = None
    if module.has(PERM_CORRECTIONS_REVIEW):
        pending = db.scalar(
            select(func.count()).select_from(CorrectionRequest).where(CorrectionRequest.status == CORRECTION_PENDING)
        )
    return OverviewOut(
        date=day,
        time_zone=service.policy.business_time_zone,
        server_time=now,
        working_count=sum(1 for c in cards if c.state == "WORKING"),
        on_break_count=sum(1 for c in cards if c.state == "ON_BREAK"),
        completed_today=len(completed),
        exception_count=len(exceptions),
        pending_corrections=pending,
        totals=_totals(report.summary(flt)["totals"]),
        working=[c for c in cards if c.state == "WORKING"],
        on_break=[c for c in cards if c.state == "ON_BREAK"],
        completed=[
            {
                "platform_user_id": s.platform_user_id,
                "employee_name": display_name(names, s.platform_user_id),
                "session": _session(s, now).model_dump(mode="json"),
            }
            for s in completed
        ],
        exceptions=exceptions,
    )


@router.get("/employees", response_model=EmployeeListOut)
def employees(
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _claims: AuthClaims = Depends(can_read),
    db: Session = Depends(get_db),
) -> EmployeeListOut:
    criteria = []
    if q and q.strip():
        escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{escaped}%"
        criteria.append(
            or_(AttendanceEmployee.full_name.ilike(like, escape="\\"), AttendanceEmployee.email.ilike(like, escape="\\"))
        )
    total = db.scalar(select(func.count()).select_from(AttendanceEmployee).where(*criteria)) or 0
    rows = db.scalars(
        select(AttendanceEmployee).where(*criteria).order_by(func.lower(AttendanceEmployee.full_name)).limit(limit).offset(offset)
    ).all()
    names = {r.platform_user_id: r for r in rows}
    open_map = {s.platform_user_id: s for s in _open_sessions(db, set(names))}
    return EmployeeListOut(total=total, limit=limit, offset=offset, items=[_employee(db, uid, names, open_map) for uid in names])


@router.get("/employees/{user_id}/attendance", response_model=EmployeeHistoryOut)
def employee_attendance(
    user_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _claims: AuthClaims = Depends(can_read),
    service: AttendanceService = Depends(_service),
) -> EmployeeHistoryOut:
    now = service.now()
    end = date_to or service.local_date(now)
    start = date_from or end - timedelta(days=service.policy.default_history_days - 1)
    checked_range(start, end)
    sessions = service.sessions_for_range(user_id, start, end)
    names = employee_names(service.db, {user_id})
    if user_id not in names and not sessions:
        raise AttendanceError("EMPLOYEE_NOT_FOUND", "No attendance records exist for this employee.", 404)
    open_map = {s.platform_user_id: s for s in _open_sessions(service.db, {user_id})}
    daily = [
        DayTotalsOut(date=day, **_totals(t).model_dump())
        for day, t in sorted(daily_totals(sessions, service.policy.zone, now).items())
        if start <= day <= end
    ]
    return EmployeeHistoryOut(
        employee=_employee(service.db, user_id, names, open_map),
        date_from=start,
        date_to=end,
        time_zone=service.policy.business_time_zone,
        total=len(sessions),
        limit=limit,
        offset=offset,
        daily_totals=daily,
        sessions=[_session(s, now) for s in sessions[offset : offset + limit]],
    )


@router.get("/sessions/{session_id}", response_model=ManagedSessionOut)
def managed_session(
    session_id: str, _claims: AuthClaims = Depends(can_read), service: AttendanceService = Depends(_service)
) -> ManagedSessionOut:
    session = service.db.get(AttendanceSession, session_id)
    if session is None:
        raise AttendanceError("SESSION_NOT_FOUND", "Attendance session not found.", 404)
    uid = session.platform_user_id
    names = employee_names(service.db, {uid})
    open_map = {s.platform_user_id: s for s in _open_sessions(service.db, {uid})}
    return ManagedSessionOut(employee=_employee(service.db, uid, names, open_map), session=_session(session, service.now()))


def _can_decide(claims: AuthClaims, item: CorrectionRequest) -> bool:
    return (
        item.status == CORRECTION_PENDING
        and claims.user_id != item.platform_user_id
        and claims.module(MODULE_ATWORK).has(PERM_CORRECTIONS_APPROVE)
    )


@router.get("/corrections", response_model=CorrectionListOut)
def correction_queue(
    status: str | None = None,
    user_id: int | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    claims: AuthClaims = Depends(can_review),
    db: Session = Depends(get_db),
) -> CorrectionListOut:
    criteria = []
    if status:
        criteria.append(CorrectionRequest.status == status)
    if user_id is not None:
        criteria.append(CorrectionRequest.platform_user_id == user_id)
    total = db.scalar(select(func.count()).select_from(CorrectionRequest).where(*criteria)) or 0
    items = db.scalars(
        select(CorrectionRequest).where(*criteria).order_by(CorrectionRequest.created_at.desc()).limit(limit).offset(offset)
    ).all()
    names = employee_names(db, {i.platform_user_id for i in items})
    return CorrectionListOut(
        total=total,
        limit=limit,
        offset=offset,
        items=[correction_out(i, names, can_decide=_can_decide(claims, i)) for i in items],
    )


@router.get("/corrections/{request_id}", response_model=CorrectionOut)
def correction_detail(request_id: str, claims: AuthClaims = Depends(can_review), db: Session = Depends(get_db)) -> CorrectionOut:
    item = db.get(CorrectionRequest, request_id)
    if item is None:
        raise AttendanceError("CORRECTION_NOT_FOUND", "Correction request not found.", 404)
    return correction_out(item, employee_names(db, {item.platform_user_id}), can_decide=_can_decide(claims, item))


@router.post("/corrections/{request_id}/approve", response_model=CorrectionOut)
def approve(
    request_id: str,
    body: ApproveIn,
    claims: AuthClaims = Depends(can_approve),
    db: Session = Depends(get_db),
    service: CorrectionService = Depends(get_correction_service),
) -> CorrectionOut:
    item = service.approve(request_id, claims.user_id, claims.full_name, body.note)
    return correction_out(item, employee_names(db, {item.platform_user_id}))


@router.post("/corrections/{request_id}/reject", response_model=CorrectionOut)
def reject(
    request_id: str,
    body: RejectIn,
    claims: AuthClaims = Depends(can_approve),
    db: Session = Depends(get_db),
    service: CorrectionService = Depends(get_correction_service),
) -> CorrectionOut:
    item = service.reject(request_id, claims.user_id, claims.full_name, body.reason)
    return correction_out(item, employee_names(db, {item.platform_user_id}))


@router.get("/audit", response_model=AuditListOut)
def audit(
    action: str | None = None,
    user_id: int | None = None,
    session_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _claims: AuthClaims = Depends(can_audit),
    db: Session = Depends(get_db),
    policy: AttendancePolicy = Depends(get_policy),
) -> AuditListOut:
    criteria = []
    if action:
        criteria.append(AttendanceEvent.action == action)
    if user_id is not None:
        criteria.append(AttendanceEvent.subject_user_id == user_id)
    if session_id:
        criteria.append(AttendanceEvent.session_id == session_id)
    if date_from and date_to:
        checked_range(date_from, date_to)
    if date_from:
        criteria.append(AttendanceEvent.occurred_at >= local_day_bounds(date_from, policy.zone)[0])
    if date_to:
        criteria.append(AttendanceEvent.occurred_at < local_day_bounds(date_to, policy.zone)[1])
    total = db.scalar(select(func.count()).select_from(AttendanceEvent).where(*criteria)) or 0
    rows = db.scalars(
        select(AttendanceEvent)
        .where(*criteria)
        .order_by(AttendanceEvent.occurred_at.desc(), AttendanceEvent.id)
        .limit(limit)
        .offset(offset)
    ).all()
    names = employee_names(db, {r.actor_user_id for r in rows} | {r.subject_user_id for r in rows})
    return AuditListOut(
        total=total,
        limit=limit,
        offset=offset,
        items=[
            AuditEventOut(
                id=r.id,
                action=r.action,
                entity_type=r.entity_type,
                entity_id=r.entity_id,
                session_id=r.session_id,
                actor_user_id=r.actor_user_id,
                actor_name=display_name(names, r.actor_user_id),
                subject_user_id=r.subject_user_id,
                subject_name=display_name(names, r.subject_user_id),
                occurred_at=r.occurred_at,
                before_state=r.before_state,
                after_state=r.after_state,
            )
            for r in rows
        ],
    )


def _filter(
    service: AttendanceService, date_from: date | None, date_to: date | None, user_id: int | None, work_mode: str | None
) -> ReportFilter:
    end = date_to or service.local_date(service.now())
    return ReportFilter(date_from or end - timedelta(days=29), end, user_id, work_mode)


@router.get("/reports/summary", response_model=ReportSummaryOut)
def report_summary(
    date_from: date | None = None,
    date_to: date | None = None,
    user_id: int | None = None,
    work_mode: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _claims: AuthClaims = Depends(can_report),
    service: AttendanceService = Depends(_service),
) -> ReportSummaryOut:
    flt = _filter(service, date_from, date_to, user_id, work_mode)
    data = Reporting(service.db, service.policy, service.now()).summary(flt)
    return ReportSummaryOut(
        date_from=flt.date_from,
        date_to=flt.date_to,
        time_zone=service.policy.business_time_zone,
        session_count=data["session_count"],
        totals=_totals(data["totals"]),
        by_work_mode=[ModeTotalsOut(work_mode=m, **_totals(t).model_dump()) for m, t in sorted(data["by_work_mode"].items())],
        by_day=[DayTotalsOut(date=d, **_totals(t).model_dump()) for d, t in data["by_day"].items()],
        employee_total=len(data["by_employee"]),
        limit=limit,
        offset=offset,
        by_employee=[
            EmployeeSummaryOut(
                platform_user_id=r["platform_user_id"],
                employee_name=r["employee_name"],
                session_count=r["session_count"],
                totals=_totals(r["totals"]),
            )
            for r in data["by_employee"][offset : offset + limit]
        ],
    )


@router.get("/reports/missed-checkouts", response_model=MissedCheckoutReportOut)
def report_missed(
    date_from: date | None = None,
    date_to: date | None = None,
    user_id: int | None = None,
    work_mode: str | None = None,
    _claims: AuthClaims = Depends(can_report),
    service: AttendanceService = Depends(_service),
) -> MissedCheckoutReportOut:
    flt = _filter(service, date_from, date_to, user_id, work_mode)
    rows = Reporting(service.db, service.policy, service.now()).missed_checkouts(flt)
    return MissedCheckoutReportOut(
        threshold_hours=service.policy.missed_checkout_hours, total=len(rows), items=[MissedCheckoutOut(**r) for r in rows]
    )


@router.get("/reports/corrections", response_model=CorrectionReportOut)
def report_corrections(
    date_from: date | None = None,
    date_to: date | None = None,
    user_id: int | None = None,
    _claims: AuthClaims = Depends(can_report),
    service: AttendanceService = Depends(_service),
) -> CorrectionReportOut:
    flt = _filter(service, date_from, date_to, user_id, None)
    items = Reporting(service.db, service.policy, service.now()).corrections(flt)
    return CorrectionReportOut(total=len(items), by_status=dict(Counter(i.status for i in items)))


_MEDIA = {"csv": "text/csv; charset=utf-8", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


@router.get("/reports/export")
def report_export(
    report: str = Query(pattern="^(employee_summary|sessions|missed_checkouts|corrections)$"),
    format: str = Query(pattern="^(csv|xlsx)$"),  # noqa: A002
    date_from: date | None = None,
    date_to: date | None = None,
    user_id: int | None = None,
    work_mode: str | None = None,
    claims: AuthClaims = Depends(can_export),
    _can_read_reports: AuthClaims = Depends(can_report),
    service: AttendanceService = Depends(_service),
) -> Response:
    flt = _filter(service, date_from, date_to, user_id, work_mode)
    now = service.now()
    head, rows = Reporting(service.db, service.policy, now).table(report, flt)
    content = to_csv(head, rows) if format == "csv" else to_xlsx(head, rows, report)
    service.db.add(
        AttendanceEvent(
            actor_user_id=claims.user_id,
            subject_user_id=user_id if user_id is not None else claims.user_id,
            action="REPORT_EXPORTED",
            entity_type="Report",
            entity_id=new_id(),
            occurred_at=now,
            after_state={
                "report": report,
                "format": format,
                "date_from": flt.date_from.isoformat(),
                "date_to": flt.date_to.isoformat(),
                "user_id": user_id,
                "work_mode": work_mode,
                "rows": len(rows),
            },
        )
    )
    service.db.commit()
    filename = f"dijiatwork-{report}-{stamp(now)}.{format}"
    return Response(content, media_type=_MEDIA[format], headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _settings_out(policy: AttendancePolicy) -> SettingsOut:
    return SettingsOut(
        enabled_work_modes=list(policy.enabled_work_modes),
        business_time_zone=policy.business_time_zone,
        missed_checkout_hours=policy.missed_checkout_hours,
        time_format=policy.time_format,
        default_history_days=policy.default_history_days,
        version=policy.settings_version,
    )


@router.get("/settings", response_model=SettingsOut)
def read_settings(
    _claims: AuthClaims = Depends(can_manage_settings), policy: AttendancePolicy = Depends(get_policy)
) -> SettingsOut:
    return _settings_out(policy)


@router.put("/settings", response_model=SettingsOut)
def update_settings(
    body: SettingsIn,
    claims: AuthClaims = Depends(can_manage_settings),
    db: Session = Depends(get_db),
    policy: AttendancePolicy = Depends(get_policy),
) -> SettingsOut:
    try:
        ZoneInfo(body.business_time_zone)
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        raise AttendanceError("INVALID_TIME_ZONE", "Enter a valid IANA time zone, such as Asia/Colombo.", 422) from exc
    before = _settings_out(policy).model_dump()
    values = body.model_dump(exclude={"version"})
    values["enabled_work_modes"] = list(dict.fromkeys(body.enabled_work_modes))
    try:
        # Compared with the row read here, not the earlier policy snapshot.
        row = db.scalars(select(AtworkSettings).where(AtworkSettings.id == 1).with_for_update()).first()
        if (row.version if row else 0) != body.version:
            raise AttendanceError("SETTINGS_CONFLICT", "Settings were changed by someone else. Reload and try again.")
        if row is None:
            db.add(AtworkSettings(id=1, updated_by_user_id=claims.user_id, **values))
        else:
            for key, value in values.items():
                setattr(row, key, value)
            row.updated_by_user_id = claims.user_id
        db.add(
            AttendanceEvent(
                actor_user_id=claims.user_id,
                subject_user_id=claims.user_id,
                action="SETTINGS_UPDATED",
                entity_type="Settings",
                entity_id="1",
                occurred_at=utcnow().replace(microsecond=0),
                before_state=before,
                after_state=values,
            )
        )
        db.commit()
    except (IntegrityError, StaleDataError) as exc:
        db.rollback()
        raise AttendanceError("SETTINGS_CONFLICT", "Settings were changed by someone else. Reload and try again.") from exc
    return _settings_out(get_policy(db))
