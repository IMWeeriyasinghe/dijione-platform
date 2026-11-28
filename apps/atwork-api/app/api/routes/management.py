"""Management APIs: organization-wide visibility, each behind an explicit permission."""

from collections import Counter
from datetime import date, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from auth_client_py import AuthClaims
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.api.deps import ManagementScope, management_scope, require_access_manage_permission, require_management_permission
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
from app.models.bp import AtworkBPGrant, AtworkBPEmployeeScope
from app.models.corrections import AttendanceEmployee, AtworkSettings, CorrectionRequest
from app.schemas.attendance import DayTotalsOut
from app.schemas.corrections import ApproveIn, CorrectionListOut, CorrectionOut, RejectIn
from app.schemas.management import (
    AnalyticsOut,
    AuditEventOut,
    AuditListOut,
    BPGrantIn,
    BPGrantOut,
    BPListOut,
    BPScopeAssignIn,
    BPScopeEmployeeOut,
    ClientAdoptionOut,
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
    SessionReportItemOut,
    SessionsReportOut,
    SettingsIn,
    SettingsOut,
)
from app.services import notifications
from app.services.attendance_policy import AttendancePolicy, get_policy
from app.services.attendance_service import AttendanceService, Clock
from app.services.correction_service import CorrectionService
from app.services.bp_service import assign_employee_to_bp, grant_bp, list_active_bps, remove_employee_from_bp, revoke_bp
from app.services.employee_directory import display_name, employee_names
from app.services.reporting import ExportInfo, ReportFilter, Reporting, checked_range, export_filename, to_csv, to_xlsx
from app.services.workforce_client import resolve_client_for_users
from app.services.time_accounting import daily_totals, local_day_bounds

router = APIRouter(prefix="/api/atwork/management", tags=["management"])

can_read = require_management_permission(PERM_ATTENDANCE_READ)
can_review = require_management_permission(PERM_CORRECTIONS_REVIEW)
can_approve = require_management_permission(PERM_CORRECTIONS_APPROVE)
can_report = require_management_permission(PERM_REPORTS_READ)
can_export = require_management_permission(PERM_REPORTS_EXPORT)
can_manage_settings = require_management_permission(PERM_SETTINGS_MANAGE)
can_audit = require_management_permission(PERM_AUDIT_READ)
can_access_manage = require_access_manage_permission()

# BP-aware dependency factories
bp_read = management_scope(PERM_ATTENDANCE_READ)
bp_report = management_scope(PERM_REPORTS_READ)
bp_export = management_scope(PERM_REPORTS_EXPORT)
bp_review = management_scope(PERM_CORRECTIONS_REVIEW)
bp_approve = management_scope(PERM_CORRECTIONS_APPROVE)


def _service(
    db: Session = Depends(get_db), policy: AttendancePolicy = Depends(get_policy), clock: Clock = Depends(get_clock)
) -> AttendanceService:
    return AttendanceService(db, policy, clock)


def _employee(
    db: Session,
    user_id: int,
    names: dict,
    open_map: dict[int, AttendanceSession],
    client_map: dict[int, str] | None = None,
) -> EmployeeOut:
    row = names.get(user_id)
    return EmployeeOut(
        platform_user_id=user_id,
        employee_name=display_name(names, user_id),
        email=row.email if row else None,
        client=client_map.get(user_id, "") if client_map else "",
        state=_state(open_map.get(user_id)),
    )


def _open_sessions(db: Session, user_ids: set[int] | None = None, scope: frozenset[int] | None = None) -> list[AttendanceSession]:
    stmt = select(AttendanceSession).where(AttendanceSession.status == STATUS_OPEN)
    effective = user_ids
    if scope is not None:
        effective = (user_ids & scope) if user_ids else scope
    if effective is not None:
        stmt = stmt.where(AttendanceSession.platform_user_id.in_(effective))
    return list(db.scalars(stmt.order_by(AttendanceSession.check_in_at)))


@router.get("/overview", response_model=OverviewOut)
def overview(ms: ManagementScope = Depends(bp_read), service: AttendanceService = Depends(_service)) -> OverviewOut:
    db, now, claims = service.db, service.now(), ms.claims
    scope = ms.scope
    day = service.local_date(now)
    report = Reporting(db, service.policy, now)
    flt = ReportFilter(day, day, user_ids=scope)
    today = report.sessions(flt)
    live = _open_sessions(db, scope=scope)
    names = employee_names(db, {s.platform_user_id for s in [*today, *live]})
    cutoff = now - timedelta(hours=service.policy.missed_checkout_hours)

    def card(session: AttendanceSession) -> LiveEmployeeOut:
        state = _state(session)
        return LiveEmployeeOut(
            platform_user_id=session.platform_user_id,
            employee_name=display_name(names, session.platform_user_id),
            state=state,
            session=_session(session, now, service.policy.unverified_after_seconds),
            overdue=session.check_in_at <= cutoff,
        )

    cards = [card(s) for s in live]
    completed = [s for s in today if s.status == STATUS_COMPLETED]
    mc_flt = ReportFilter(day, day, user_ids=scope) if scope is not None else None
    exceptions = [MissedCheckoutOut(**row) for row in report.missed_checkouts(mc_flt)]
    module = claims.module(MODULE_ATWORK)
    pending = None
    if module.has(PERM_CORRECTIONS_REVIEW):
        pend_stmt = select(func.count()).select_from(CorrectionRequest).where(CorrectionRequest.status == CORRECTION_PENDING)
        if scope is not None:
            pend_stmt = pend_stmt.where(CorrectionRequest.platform_user_id.in_(scope))
        pending = db.scalar(pend_stmt)
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
                "session": _session(s, now, service.policy.unverified_after_seconds).model_dump(mode="json"),
            }
            for s in completed
        ],
        exceptions=exceptions,
    )


@router.get("/employees", response_model=EmployeeListOut)
def employees(
    q: str | None = Query(default=None, max_length=100),
    client: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    ms: ManagementScope = Depends(bp_read),
    db: Session = Depends(get_db),
) -> EmployeeListOut:
    criteria = []
    if q and q.strip():
        escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{escaped}%"
        criteria.append(
            or_(AttendanceEmployee.full_name.ilike(like, escape="\\"), AttendanceEmployee.email.ilike(like, escape="\\"))
        )
    # BP scope filter
    if ms.scope is not None:
        if not ms.scope:
            return EmployeeListOut(total=0, limit=limit, offset=offset, items=[])
        criteria.append(AttendanceEmployee.platform_user_id.in_(ms.scope))

    total = db.scalar(select(func.count()).select_from(AttendanceEmployee).where(*criteria)) or 0
    rows = db.scalars(
        select(AttendanceEmployee).where(*criteria).order_by(func.lower(AttendanceEmployee.full_name)).limit(limit).offset(offset)
    ).all()
    names = {r.platform_user_id: r for r in rows}
    open_map = {s.platform_user_id: s for s in _open_sessions(db, set(names))}
    client_map = resolve_client_for_users(db, set(names.keys()))
    # Apply client filter if provided (after resolving clients)
    if client and client.strip():
        c = client.strip().lower()
        filtered_ids = {uid for uid, cl in client_map.items() if cl.lower() == c}
        names = {uid: row for uid, row in names.items() if uid in filtered_ids}
        total = len(names)  # recount after client filter
    return EmployeeListOut(total=total, limit=limit, offset=offset, items=[_employee(db, uid, names, open_map, client_map) for uid in names])


@router.get("/employees/{user_id}/attendance", response_model=EmployeeHistoryOut)
def employee_attendance(
    user_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    ms: ManagementScope = Depends(bp_read),
    service: AttendanceService = Depends(_service),
) -> EmployeeHistoryOut:
    if ms.scope is not None and user_id not in ms.scope:
        raise AttendanceError("EMPLOYEE_NOT_FOUND", "No attendance records exist for this employee.", 404)
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
        for day, t in sorted(daily_totals(sessions, service.policy.zone, now, service.policy.unverified_after_seconds).items())
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
        sessions=[_session(s, now, service.policy.unverified_after_seconds) for s in sessions[offset : offset + limit]],
    )


@router.get("/sessions/{session_id}", response_model=ManagedSessionOut)
def managed_session(
    session_id: str, ms: ManagementScope = Depends(bp_read), service: AttendanceService = Depends(_service)
) -> ManagedSessionOut:
    session = service.db.get(AttendanceSession, session_id)
    if session is None:
        raise AttendanceError("SESSION_NOT_FOUND", "Attendance session not found.", 404)
    uid = session.platform_user_id
    if ms.scope is not None and uid not in ms.scope:
        raise AttendanceError("SESSION_NOT_FOUND", "Attendance session not found.", 404)
    names = employee_names(service.db, {uid})
    open_map = {s.platform_user_id: s for s in _open_sessions(service.db, {uid})}
    return ManagedSessionOut(
        employee=_employee(service.db, uid, names, open_map),
        session=_session(session, service.now(), service.policy.unverified_after_seconds),
    )


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
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    ms: ManagementScope = Depends(bp_review),
    db: Session = Depends(get_db),
) -> CorrectionListOut:
    claims = ms.claims
    criteria = []
    if status:
        criteria.append(CorrectionRequest.status == status)
    if user_id is not None:
        criteria.append(CorrectionRequest.platform_user_id == user_id)
    # BP scope
    if ms.scope is not None:
        if not ms.scope:
            return CorrectionListOut(total=0, limit=limit, offset=offset, items=[])
        criteria.append(CorrectionRequest.platform_user_id.in_(ms.scope))
    if date_from is not None:
        criteria.append(CorrectionRequest.created_at >= date_from)
    if date_to is not None:
        criteria.append(CorrectionRequest.created_at < date_to + timedelta(days=1))
    all_items = db.scalars(
        select(CorrectionRequest).where(*criteria).order_by(CorrectionRequest.created_at.desc())
    ).all()
    names = employee_names(db, {i.platform_user_id for i in all_items})
    if q:
        q_lower = q.strip().lower()
        all_items = [i for i in all_items if q_lower in display_name(names, i.platform_user_id).lower()]
    total = len(all_items)
    items = all_items[offset : offset + limit]
    return CorrectionListOut(
        total=total,
        limit=limit,
        offset=offset,
        items=[correction_out(i, names, can_decide=_can_decide(claims, i)) for i in items],
    )


@router.get("/corrections/{request_id}", response_model=CorrectionOut)
def correction_detail(request_id: str, ms: ManagementScope = Depends(bp_review), db: Session = Depends(get_db)) -> CorrectionOut:
    claims = ms.claims
    item = db.get(CorrectionRequest, request_id)
    if item is None:
        raise AttendanceError("CORRECTION_NOT_FOUND", "Correction request not found.", 404)
    if ms.scope is not None and item.platform_user_id not in ms.scope:
        raise AttendanceError("CORRECTION_NOT_FOUND", "Correction request not found.", 404)
    return correction_out(item, employee_names(db, {item.platform_user_id}), can_decide=_can_decide(claims, item))


@router.post("/corrections/{request_id}/approve", response_model=CorrectionOut)
def approve(
    request_id: str,
    body: ApproveIn,
    background: BackgroundTasks,
    ms: ManagementScope = Depends(bp_approve),
    db: Session = Depends(get_db),
    service: CorrectionService = Depends(get_correction_service),
) -> CorrectionOut:
    claims = ms.claims
    if ms.scope is not None:
        item = db.get(CorrectionRequest, request_id)
        if item and item.platform_user_id not in ms.scope:
            raise AttendanceError("CORRECTION_NOT_FOUND", "Correction request not found.", 404)
    item = service.approve(request_id, claims.user_id, claims.full_name, body.note)
    background.add_task(notifications.deliver_after_response)
    return correction_out(item, employee_names(db, {item.platform_user_id}))


@router.post("/corrections/{request_id}/reject", response_model=CorrectionOut)
def reject(
    request_id: str,
    body: RejectIn,
    background: BackgroundTasks,
    ms: ManagementScope = Depends(bp_approve),
    db: Session = Depends(get_db),
    service: CorrectionService = Depends(get_correction_service),
) -> CorrectionOut:
    claims = ms.claims
    if ms.scope is not None:
        item = db.get(CorrectionRequest, request_id)
        if item and item.platform_user_id not in ms.scope:
            raise AttendanceError("CORRECTION_NOT_FOUND", "Correction request not found.", 404)
    item = service.reject(request_id, claims.user_id, claims.full_name, body.reason)
    background.add_task(notifications.deliver_after_response)
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
    service: AttendanceService,
    date_from: date | None,
    date_to: date | None,
    user_id: int | None,
    work_mode: str | None,
    scope: frozenset[int] | None = None,
    client: str | None = None,
) -> ReportFilter:
    end = date_to or service.local_date(service.now())
    return ReportFilter(date_from or end - timedelta(days=29), end, user_id, work_mode, scope, client or None)


_EMPLOYEE_SORT = {"employee_name", "session_count", "net", "gross", "unverified"}
_SESSION_SORT = {"check_in_at", "employee_name", "work_mode", "status", "net"}


def _sort_employees(employees: list[dict], sort_by: str, sort_dir: str) -> list[dict]:
    reverse = sort_dir == "desc"
    if sort_by == "session_count":
        return sorted(employees, key=lambda e: e["session_count"], reverse=reverse)
    if sort_by == "net":
        return sorted(employees, key=lambda e: e["totals"].net_seconds, reverse=reverse)
    if sort_by == "gross":
        return sorted(employees, key=lambda e: e["totals"].gross_seconds, reverse=reverse)
    if sort_by == "unverified":
        return sorted(employees, key=lambda e: e["totals"].provisional_seconds, reverse=reverse)
    return sorted(employees, key=lambda e: e["employee_name"].lower(), reverse=reverse)


def _employee_out(r: dict) -> EmployeeSummaryOut:
    return EmployeeSummaryOut(
        platform_user_id=r["platform_user_id"],
        employee_name=r["employee_name"],
        client=r.get("client", ""),
        session_count=r["session_count"],
        totals=_totals(r["totals"]),
    )


@router.get("/reports/summary", response_model=ReportSummaryOut)
def report_summary(
    date_from: date | None = None,
    date_to: date | None = None,
    user_id: int | None = None,
    work_mode: str | None = None,
    client: str | None = None,
    q: str | None = None,
    sort_by: str = Query(default="employee_name"),
    sort_dir: str = Query(default="asc", pattern="^(asc|desc)$"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    ms: ManagementScope = Depends(bp_report),
    service: AttendanceService = Depends(_service),
) -> ReportSummaryOut:
    flt = _filter(service, date_from, date_to, user_id, work_mode, ms.scope, client)
    data = Reporting(service.db, service.policy, service.now()).summary(flt)
    employees = data["by_employee"]
    # Enrich client for each employee row
    all_uids = {r["platform_user_id"] for r in employees}
    client_map = resolve_client_for_users(service.db, all_uids) if all_uids else {}
    for emp in employees:
        emp["client"] = client_map.get(emp["platform_user_id"], "")
    if client:
        employees = [e for e in employees if e["client"] == client]
    if q:
        q_lower = q.strip().lower()
        employees = [e for e in employees if q_lower in e["employee_name"].lower()]
    sort_key = sort_by if sort_by in _EMPLOYEE_SORT else "employee_name"
    employees = _sort_employees(employees, sort_key, sort_dir)
    chart_employees = sorted(employees, key=lambda e: e["totals"].net_seconds, reverse=True)[:8]
    return ReportSummaryOut(
        date_from=flt.date_from,
        date_to=flt.date_to,
        time_zone=service.policy.business_time_zone,
        session_count=data["session_count"],
        totals=_totals(data["totals"]),
        by_work_mode=[ModeTotalsOut(work_mode=m, **_totals(t).model_dump()) for m, t in sorted(data["by_work_mode"].items())],
        by_day=[DayTotalsOut(date=d, **_totals(t).model_dump()) for d, t in data["by_day"].items()],
        employee_total=len(employees),
        limit=limit,
        offset=offset,
        chart_employees=[_employee_out(r) for r in chart_employees],
        by_employee=[_employee_out(r) for r in employees[offset : offset + limit]],
    )


@router.get("/reports/missed-checkouts", response_model=MissedCheckoutReportOut)
def report_missed(
    date_from: date | None = None,
    date_to: date | None = None,
    user_id: int | None = None,
    work_mode: str | None = None,
    ms: ManagementScope = Depends(bp_report),
    service: AttendanceService = Depends(_service),
) -> MissedCheckoutReportOut:
    flt = _filter(service, date_from, date_to, user_id, work_mode, ms.scope)
    rows = Reporting(service.db, service.policy, service.now()).missed_checkouts(flt)
    return MissedCheckoutReportOut(
        threshold_hours=service.policy.missed_checkout_hours, total=len(rows), items=[MissedCheckoutOut(**r) for r in rows]
    )


@router.get("/reports/sessions", response_model=SessionsReportOut)
def report_sessions(
    date_from: date | None = None,
    date_to: date | None = None,
    user_id: int | None = None,
    work_mode: str | None = None,
    client: str | None = None,
    q: str | None = None,
    sort_by: str = Query(default="check_in_at"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    ms: ManagementScope = Depends(bp_report),
    service: AttendanceService = Depends(_service),
) -> SessionsReportOut:
    flt = _filter(service, date_from, date_to, user_id, work_mode, ms.scope, client)
    now = service.now()
    reporter = Reporting(service.db, service.policy, now)
    sessions = reporter.sessions(flt)
    names = employee_names(service.db, {s.platform_user_id for s in sessions})
    if q:
        q_lower = q.strip().lower()
        sessions = [s for s in sessions if q_lower in display_name(names, s.platform_user_id).lower()]
    # Full-dataset aggregates before pagination
    by_status: dict[str, int] = {}
    by_mode: dict[str, int] = {}
    for s in sessions:
        by_status[s.status] = by_status.get(s.status, 0) + 1
        by_mode[s.work_mode] = by_mode.get(s.work_mode, 0) + 1
    # Sort before pagination
    sk = sort_by if sort_by in _SESSION_SORT else "check_in_at"
    reverse = sort_dir == "desc"
    if sk == "employee_name":
        sessions = sorted(sessions, key=lambda s: display_name(names, s.platform_user_id).lower(), reverse=reverse)
    elif sk == "work_mode":
        sessions = sorted(sessions, key=lambda s: s.work_mode, reverse=reverse)
    elif sk == "status":
        sessions = sorted(sessions, key=lambda s: s.status, reverse=reverse)
    elif sk == "net":
        sessions = sorted(sessions, key=lambda s: reporter.in_range(s, flt).net_seconds, reverse=reverse)
    else:
        sessions = sorted(sessions, key=lambda s: s.check_in_at, reverse=reverse)
    items = [
        SessionReportItemOut(
            platform_user_id=s.platform_user_id,
            employee_name=display_name(names, s.platform_user_id),
            session=_session(s, now, service.policy.unverified_after_seconds),
            period_totals=_totals(reporter.in_range(s, flt)),
        )
        for s in sessions[offset : offset + limit]
    ]
    return SessionsReportOut(
        date_from=flt.date_from,
        date_to=flt.date_to,
        time_zone=service.policy.business_time_zone,
        total=len(sessions),
        limit=limit,
        offset=offset,
        by_status=by_status,
        by_mode=by_mode,
        items=items,
    )


@router.get("/reports/corrections", response_model=CorrectionReportOut)
def report_corrections(
    date_from: date | None = None,
    date_to: date | None = None,
    user_id: int | None = None,
    ms: ManagementScope = Depends(bp_report),
    service: AttendanceService = Depends(_service),
) -> CorrectionReportOut:
    flt = _filter(service, date_from, date_to, user_id, None, ms.scope)
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
    client: str | None = None,
    q: str | None = None,
    ms: ManagementScope = Depends(bp_export),
    service: AttendanceService = Depends(_service),
) -> Response:
    claims = ms.claims
    # Full managers need reports.read as well as reports.export
    if ms.scope is None:
        module_claim = claims.module(MODULE_ATWORK)
        if module_claim is None or not module_claim.has(PERM_REPORTS_READ):
            from fastapi import HTTPException, status
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing required permission: {PERM_REPORTS_READ}")
    flt = _filter(service, date_from, date_to, user_id, work_mode, ms.scope, client)
    now = service.now()
    head, rows = Reporting(service.db, service.policy, now).table(report, flt, name_filter=q or None)
    info = ExportInfo(
        report,
        flt.date_from,
        flt.date_to,
        now.astimezone(service.policy.zone),
        service.policy.business_time_zone,
        user_id,
        work_mode,
    )
    content = to_csv(head, rows, info) if format == "csv" else to_xlsx(head, rows, info)
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
    filename = export_filename(info, format)
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


# ---------------------------------------------------------------------------
# Analytics: adoption by client
# ---------------------------------------------------------------------------

@router.get("/analytics", response_model=AnalyticsOut)
def analytics(
    date_from: date | None = None,
    date_to: date | None = None,
    ms: ManagementScope = Depends(bp_read),
    service: AttendanceService = Depends(_service),
) -> AnalyticsOut:
    """Client-level adoption, office/remote split and confirmed hours."""
    from app.services.time_accounting import Totals as _Totals
    flt = _filter(service, date_from, date_to, None, None, ms.scope)
    reporter = Reporting(service.db, service.policy, service.now())
    sessions = reporter.sessions(flt)

    # Resolve client for every employee in the result set
    all_uids = {s.platform_user_id for s in sessions}
    client_map = resolve_client_for_users(service.db, all_uids) if all_uids else {}

    # Aggregate per client
    class _Agg:
        def __init__(self) -> None:
            self.users: set[int] = set()
            self.office = 0
            self.remote = 0
            self.net_s = 0.0
            self.unverified_s = 0.0

    agg: dict[str, _Agg] = {}
    for s in sessions:
        c = client_map.get(s.platform_user_id, "")
        a = agg.setdefault(c, _Agg())
        a.users.add(s.platform_user_id)
        part = reporter.in_range(s, flt)
        if s.work_mode == "OFFICE":
            a.office += 1
        else:
            a.remote += 1
        a.net_s += part.net_seconds
        a.unverified_s += part.provisional_seconds

    # Eligible employees: anyone who had a session in scope
    by_client = sorted(
        [
            ClientAdoptionOut(
                client=c or "(Unassigned)",
                eligible_employees=len(a.users),
                adopted_employees=len(a.users),
                adoption_pct=100.0,
                office_sessions=a.office,
                remote_sessions=a.remote,
                net_hours=round(a.net_s / 3600, 2),
                unverified_hours=round(a.unverified_s / 3600, 2),
            )
            for c, a in agg.items()
        ],
        key=lambda x: x.client,
    )
    return AnalyticsOut(
        date_from=flt.date_from,
        date_to=flt.date_to,
        time_zone=service.policy.business_time_zone,
        by_client=by_client,
    )


# ---------------------------------------------------------------------------
# BP Access Management endpoints
# ---------------------------------------------------------------------------

@router.get("/bp", response_model=BPListOut)
def list_bps(
    _claims: AuthClaims = Depends(can_access_manage),
    db: Session = Depends(get_db),
) -> BPListOut:
    return BPListOut(items=[BPGrantOut(**r) for r in list_active_bps(db)])


@router.post("/bp", response_model=BPGrantOut, status_code=201)
def create_bp(
    body: BPGrantIn,
    claims: AuthClaims = Depends(can_access_manage),
    db: Session = Depends(get_db),
) -> BPGrantOut:
    grant = grant_bp(db, body.target_user_id, claims.user_id)
    emp = db.get(AttendanceEmployee, grant.platform_user_id)
    return BPGrantOut(
        platform_user_id=grant.platform_user_id,
        full_name=emp.full_name if emp else f"User #{grant.platform_user_id}",
        work_email=emp.email if emp else None,
        employee_count=0,
        granted_at=grant.granted_at,
        granted_by=grant.granted_by,
    )


@router.post("/bp/{bp_user_id}/revoke", status_code=204)
def revoke_bp_access(
    bp_user_id: int,
    claims: AuthClaims = Depends(can_access_manage),
    db: Session = Depends(get_db),
) -> None:
    if not revoke_bp(db, bp_user_id, claims.user_id):
        raise AttendanceError("BP_NOT_FOUND", "Active BP grant not found.", 404)


@router.get("/bp/{bp_user_id}/scope", response_model=list[BPScopeEmployeeOut])
def get_bp_scope(
    bp_user_id: int,
    _claims: AuthClaims = Depends(can_access_manage),
    db: Session = Depends(get_db),
) -> list[BPScopeEmployeeOut]:
    from app.services.bp_service import get_bp_employee_scope
    employee_ids = get_bp_employee_scope(db, bp_user_id)
    if not employee_ids:
        return []
    names = employee_names(db, set(employee_ids))
    client_map = resolve_client_for_users(db, set(employee_ids))
    result = []
    for uid in sorted(employee_ids):
        row = names.get(uid)
        result.append(BPScopeEmployeeOut(
            platform_user_id=uid,
            employee_name=display_name(names, uid),
            work_email=row.email if row else None,
            client=client_map.get(uid, ""),
        ))
    return result


@router.post("/bp/{bp_user_id}/scope", status_code=201)
def add_bp_scope_employee(
    bp_user_id: int,
    body: BPScopeAssignIn,
    claims: AuthClaims = Depends(can_access_manage),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.bp_service import is_bp
    if not is_bp(db, bp_user_id):
        raise AttendanceError("BP_NOT_FOUND", "Active BP grant not found.", 404)
    assign_employee_to_bp(db, bp_user_id, body.employee_user_id, claims.user_id)
    return {"bp_user_id": bp_user_id, "employee_user_id": body.employee_user_id}


@router.delete("/bp/{bp_user_id}/scope/{employee_user_id}", status_code=204)
def remove_bp_scope_employee(
    bp_user_id: int,
    employee_user_id: int,
    claims: AuthClaims = Depends(can_access_manage),
    db: Session = Depends(get_db),
) -> None:
    if not remove_employee_from_bp(db, bp_user_id, employee_user_id, claims.user_id):
        raise AttendanceError("SCOPE_NOT_FOUND", "Employee scope assignment not found.", 404)
