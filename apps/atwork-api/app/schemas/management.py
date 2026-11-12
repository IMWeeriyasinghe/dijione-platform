from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.attendance import DayTotalsOut, SessionOut, TotalsOut, WorkMode


class LiveEmployeeOut(BaseModel):
    platform_user_id: int
    employee_name: str
    state: Literal["WORKING", "ON_BREAK"]
    session: SessionOut
    overdue: bool


class MissedCheckoutOut(BaseModel):
    session_id: str
    platform_user_id: int
    employee_name: str
    work_mode: WorkMode
    check_in_at: datetime
    open_seconds: int
    break_open: bool


class CompletedSessionOut(BaseModel):
    platform_user_id: int
    employee_name: str
    session: SessionOut


class OverviewOut(BaseModel):
    date: date
    time_zone: str
    server_time: datetime
    working_count: int
    on_break_count: int
    completed_today: int
    exception_count: int
    pending_corrections: int | None
    totals: TotalsOut
    working: list[LiveEmployeeOut]
    on_break: list[LiveEmployeeOut]
    completed: list[CompletedSessionOut]
    exceptions: list[MissedCheckoutOut]


class EmployeeOut(BaseModel):
    platform_user_id: int
    employee_name: str
    email: str | None
    state: Literal["NOT_CHECKED_IN", "WORKING", "ON_BREAK"]


class EmployeeListOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[EmployeeOut]


class EmployeeHistoryOut(BaseModel):
    employee: EmployeeOut
    date_from: date
    date_to: date
    time_zone: str
    total: int
    limit: int
    offset: int
    daily_totals: list[DayTotalsOut]
    sessions: list[SessionOut]


class ManagedSessionOut(BaseModel):
    employee: EmployeeOut
    session: SessionOut


class AuditEventOut(BaseModel):
    id: str
    action: str
    entity_type: str
    entity_id: str
    session_id: str | None
    actor_user_id: int
    actor_name: str
    subject_user_id: int
    subject_name: str
    occurred_at: datetime
    before_state: dict | None
    after_state: dict | None


class AuditListOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AuditEventOut]


class EmployeeSummaryOut(BaseModel):
    platform_user_id: int
    employee_name: str
    session_count: int
    totals: TotalsOut


class ModeTotalsOut(TotalsOut):
    work_mode: WorkMode


class ReportSummaryOut(BaseModel):
    date_from: date
    date_to: date
    time_zone: str
    session_count: int
    totals: TotalsOut
    by_work_mode: list[ModeTotalsOut]
    by_day: list[DayTotalsOut]
    employee_total: int
    limit: int
    offset: int
    by_employee: list[EmployeeSummaryOut]


class MissedCheckoutReportOut(BaseModel):
    threshold_hours: int
    total: int
    items: list[MissedCheckoutOut]


class CorrectionReportOut(BaseModel):
    total: int
    by_status: dict[str, int]


class SettingsOut(BaseModel):
    enabled_work_modes: list[WorkMode]
    business_time_zone: str
    missed_checkout_hours: int
    time_format: Literal["24h", "12h"]
    default_history_days: int
    version: int


class SettingsIn(BaseModel):
    enabled_work_modes: list[WorkMode] = Field(min_length=1)
    business_time_zone: str = Field(min_length=1, max_length=64)
    missed_checkout_hours: int = Field(ge=1, le=72)
    time_format: Literal["24h", "12h"]
    default_history_days: int = Field(ge=7, le=90)
    version: int = Field(ge=0)
