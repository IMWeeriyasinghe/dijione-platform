"""Provider-shaped DTO for an employee, sourced from people-api's canonical
employee DTO (which is itself already-mapped BambooHR data — see
docs/platform/bamboohr-live-discovery.md for the original field survey).
birthday-api holds NO BambooHR credential and makes NO BambooHR call
(Architecture Completion Plan §3) — this is the shape ``detection_service``
/ ``directory_service`` consume, unchanged from before Wave E.
"""

from pydantic import BaseModel


class EmployeeRecord(BaseModel):
    id: str  # people-api's bamboohr_id — the stable provider id
    employee_number: str | None = None
    # first_name/last_name are optional and exist only as a mapper fallback
    # (display_name is what people-api/BambooHR actually populates and is
    # always preferred — see mapper.map_employee).
    first_name: str = ""
    last_name: str = ""
    display_name: str
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
