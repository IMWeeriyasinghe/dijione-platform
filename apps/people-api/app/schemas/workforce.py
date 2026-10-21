from __future__ import annotations

from pydantic import BaseModel


class WorkforceEntryOut(BaseModel):
    """Generic Workforce Directory DTO — minimum data (CLAUDE.md rule 9):
    no birthday, address, email or compensation."""

    bamboohr_id: str
    employee_number: str | None = None
    display_name: str
    department: str
    job_title: str
    location: str
    employment_status: str
    hire_date: str | None = None
    termination_date: str | None = None
    present_in_source: bool
    synced_at: str | None = None


class WorkforceSyncRequestIn(BaseModel):
    # Required, no default: the directory serves any consumer, so the
    # caller must identify itself.
    requested_by_application: str
    requested_by_user_id: int | None = None


class WorkforceSyncRunOut(BaseModel):
    run_id: str
    provider: str
    status: str
    trigger_type: str
    requested_by_application: str
    requested_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    records_read: int
    records_created: int
    records_updated: int
    records_unchanged: int
    records_absent: int
    error_summary: str | None = None


class WorkforceSyncAcceptedOut(BaseModel):
    run_id: str
    status: str
    started: bool
    message: str


class WorkforceFreshnessOut(BaseModel):
    provider: str
    last_successful_sync_at: str | None = None
    latest_run: WorkforceSyncRunOut | None = None
