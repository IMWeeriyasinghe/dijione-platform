"""Maps BambooHREmployee (provider vocabulary) into the plain dict shape
``app/services/detection_service.py`` consumes. Kept as a separate mapping
layer so a future live BambooHRClient's raw payloads never leak into the
detection service directly (CLAUDE.md §27's DTO-conversion rule mirrored
here for BambooHR)."""

from datetime import date

from app.integrations.bamboohr.schemas import BambooHREmployee

# BambooHR's sentinel for "no termination date" — confirmed live (never
# returns null for this field for this tenant, returns this string
# instead). Normalized to None here so callers only ever reason about
# "termination_date is None" vs. a real date.
_NO_TERMINATION_SENTINEL = "0000-00-00"


def _parse_iso_date(raw: str | None) -> date | None:
    if not raw or raw == _NO_TERMINATION_SENTINEL:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def map_employee(employee: BambooHREmployee) -> dict:
    return {
        "employee_id": employee.id,
        "employee_number": employee.employee_number or None,
        "full_name": employee.display_name or f"{employee.first_name} {employee.last_name}".strip(),
        "work_email": employee.work_email,
        "birth_month": employee.birth_month,
        "birth_day": employee.birth_day,
        "department": employee.department,
        "office_location": employee.office_location,
        "employment_status": employee.employment_status,
        "hire_date": _parse_iso_date(employee.hire_date),
        "termination_date": _parse_iso_date(employee.termination_date),
        "address_line1": employee.address_line1,
        "address_line2": employee.address_line2,
        "city": employee.city,
        "state_province": employee.state_province,
        "postal_code": employee.postal_code,
        "country": employee.country,
    }
