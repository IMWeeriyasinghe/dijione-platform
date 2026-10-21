"""Maps ``BambooHRWorkforceRecord`` (provider vocabulary) into the plain
dict shape ``WorkforceSyncService`` persists. Kept separate from
``mapper.map_employee`` (the Birthday-oriented Employee contract)."""

from datetime import date

from app.integrations.bamboohr.workforce_schemas import BambooHRWorkforceRecord

# BambooHR's sentinel for "no date" — confirmed live for terminationDate.
_NO_DATE_SENTINEL = "0000-00-00"


def _parse_iso_date(raw: str | None) -> date | None:
    if not raw or raw == _NO_DATE_SENTINEL:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def map_workforce_record(record: BambooHRWorkforceRecord) -> dict:
    return {
        "bamboohr_id": record.id,
        "employee_number": record.employee_number,
        "display_name": record.display_name,
        "department": record.department,
        "job_title": record.job_title,
        "location": record.location,
        "employment_status": record.employment_status,
        "hire_date": _parse_iso_date(record.hire_date),
        "termination_date": _parse_iso_date(record.termination_date),
    }
