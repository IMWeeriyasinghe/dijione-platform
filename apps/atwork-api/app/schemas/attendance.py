from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

WorkMode = Literal["OFFICE", "REMOTE", "CLIENT_SITE"]
RequestId = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class ActionIn(BaseModel):
    client_request_id: str = RequestId


class CheckInIn(ActionIn):
    work_mode: WorkMode


class BreakOut(BaseModel):
    id: str
    started_at: datetime
    ended_at: datetime | None


class TotalsOut(BaseModel):
    gross_seconds: int
    break_seconds: int
    net_seconds: int
    # Net time of unverified sessions, excluded from the confirmed fields above.
    provisional_seconds: int = 0


class SessionOut(BaseModel):
    id: str
    work_mode: WorkMode
    status: str
    check_in_at: datetime
    check_out_at: datetime | None
    time_zone: str
    origin: str
    correction_count: int
    breaks: list[BreakOut]
    totals: TotalsOut
    # Longer than the missed check-out threshold and not confirmed by Management.
    unverified: bool = False


class StatusOut(BaseModel):
    state: Literal["NOT_CHECKED_IN", "WORKING", "ON_BREAK"]
    server_time: datetime
    time_zone: str
    session: SessionOut | None


class ActionOut(BaseModel):
    replayed: bool
    state: Literal["NOT_CHECKED_IN", "WORKING", "ON_BREAK"]
    server_time: datetime
    session: SessionOut


class DayTotalsOut(TotalsOut):
    date: date


class TodayOut(BaseModel):
    date: date
    time_zone: str
    server_time: datetime
    session_count: int
    totals: TotalsOut
    sessions: list[SessionOut]


class HistoryOut(BaseModel):
    date_from: date
    date_to: date
    time_zone: str
    total: int
    limit: int
    offset: int
    daily_totals: list[DayTotalsOut]
    sessions: list[SessionOut]


class PolicyOut(BaseModel):
    enabled_work_modes: list[WorkMode]
    business_time_zone: str
    missed_checkout_hours: int
    time_format: str
    default_history_days: int
    server_time: datetime
