"""Maps EmployeeRecord (people-api's already-mapped shape) into the plain
dict ``app/services/detection_service.py`` / ``directory_service.py``
consume. Kept as a thin layer so those services never depend on the DTO
class directly (mirrors the pre-Wave-E bamboohr mapper's role)."""

from datetime import date

_NO_TERMINATION_SENTINEL = "0000-00-00"


def _parse_iso_date(raw: str | None) -> date | None:
    if not raw or raw == _NO_TERMINATION_SENTINEL:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def map_employee(employee) -> dict:
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
