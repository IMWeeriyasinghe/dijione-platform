"""Provider-shaped DTO for the generic Workforce Directory — mirrors
BambooHR's Custom Report vocabulary, not our domain model.

Deliberately separate from ``schemas.BambooHREmployee`` (the Birthday-
oriented Employee contract): a workforce record carries no birthday,
address or email, and is returned for every employee regardless of status
(see ``docs/platform/workforce-directory.md``). Field meanings were
verified live 2026-08-14 — see ``docs/platform/bamboohr-live-discovery.md``.
"""

from pydantic import BaseModel


class BambooHRWorkforceRecord(BaseModel):
    id: str
    # Stored exactly as BambooHR returns it (text, never cast). Can be
    # blank, and is not guaranteed unique — consumers report both cases.
    employee_number: str | None = None
    display_name: str
    department: str = ""
    job_title: str = ""
    location: str = ""
    employment_status: str  # "Active" / "Inactive" — BambooHR ``status``
    hire_date: str | None = None  # raw ISO "YYYY-MM-DD" or BambooHR's sentinel
    termination_date: str | None = None
