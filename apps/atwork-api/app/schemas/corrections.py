from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from app.schemas.attendance import RequestId, WorkMode


class ProposedBreak(BaseModel):
    started_at: AwareDatetime
    ended_at: AwareDatetime


class CorrectionIn(BaseModel):
    """``session_id`` amends a session; omitted, it requests a missing one.
    Fields left out keep their current values."""

    client_request_id: str = RequestId
    session_id: str | None = None
    reason: str = Field(min_length=5, max_length=1000)
    work_mode: WorkMode | None = None
    check_in_at: AwareDatetime | None = None
    check_out_at: AwareDatetime | None = None
    breaks: list[ProposedBreak] | None = Field(default=None, max_length=30)


class ApproveIn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class RejectIn(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)


class CorrectionOut(BaseModel):
    id: str
    platform_user_id: int
    employee_name: str
    kind: str
    status: Literal["PENDING", "APPROVED", "REJECTED", "WITHDRAWN"]
    session_id: str | None
    reason: str
    original: dict | None
    proposed: dict
    reviewer_name: str | None
    reviewed_at: datetime | None
    decision_note: str | None
    created_at: datetime
    updated_at: datetime
    can_decide: bool = False


class CorrectionListOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[CorrectionOut]
