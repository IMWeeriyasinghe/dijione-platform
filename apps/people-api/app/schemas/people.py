from __future__ import annotations

from pydantic import BaseModel


class EmployeeOut(BaseModel):
    """Canonical employee DTO — the DijiOne People / Workforce read model.
    Provider-shaped vocabulary is never returned; this is already mapped."""

    bamboohr_id: str
    employee_number: str | None = None
    full_name: str
    work_email: str
    birth_month: int
    birth_day: int
    department: str
    office_location: str
    employment_status: str
    hire_date: str | None = None
    termination_date: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state_province: str | None = None
    postal_code: str | None = None
    country: str | None = None
    synced_at: str | None = None


class SyncRequestIn(BaseModel):
    requested_by_application: str = "birthday"
    requested_by_user_id: int | None = None


class SyncRunOut(BaseModel):
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
    error_summary: str | None = None


class SyncAcceptedOut(BaseModel):
    run_id: str
    status: str
    started: bool
    message: str


class FreshnessOut(BaseModel):
    provider: str
    last_successful_sync_at: str | None = None
    latest_run: SyncRunOut | None = None
