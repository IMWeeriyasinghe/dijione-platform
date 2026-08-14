"""Provider-shaped DTO — mirrors BambooHR's employee-directory vocabulary,
not our domain model.

Field mapping verified against a real tenant (2026-08-14 live discovery,
``dijitalteam`` subdomain via the Custom Report API) — see
``docs/platform/bamboohr-live-discovery.md`` for the full field survey.
Confirmed real field names:

- ``id`` -> employee id (numeric string)
- ``displayName`` -> display_name (preferred over concatenating
  firstName/lastName — BambooHR's own display_name already handles
  preferred-name overrides)
- ``workEmail``
- ``birthday`` -> BambooHR's own derived MM-DD field (no birth year
  exposed — confirmed privacy-safe; ``dateOfBirth`` also exists tenant-side
  with a real year, but is deliberately never requested/stored here)
- ``status`` -> ``"Active"`` / ``"Inactive"`` — the single authoritative
  active/inactive field. ``employmentHistoryStatus`` was also surveyed but
  holds employment *type* (Full-Time/Part-Time/Contractor/Terminated), not
  a clean active/inactive signal, and must NOT be used for filtering.
- ``hireDate`` -> ISO date, always populated for this tenant. Confirmed
  employees can be marked ``status=Active`` in BambooHR *before* their
  hire date (9 such "future starter" records observed live) — this is why
  ``eligibility_service`` checks hire date separately from status.
- ``terminationDate`` -> ISO date, or the sentinel ``"0000-00-00"`` when
  not terminated (BambooHR does not return null here) — see
  ``mapper.map_employee`` for the sentinel-to-``None`` normalization.
- ``department`` -> for this tenant (a talent/staffing company) holds the
  client engagement/bench assignment, not a functional org department —
  passed through as-is under the ``department`` name per the DTO contract.
- ``location`` -> office/country location.
- ``employeeNumber`` -> the operational business Employee ID (BambooHR
  field type ``employee_number``), distinct from ``id`` which is
  BambooHR's own internal record identifier. Verified live 2026-08-14
  against employee "Madushanka Weeriyasinghe": ``id="366"`` (internal),
  ``employeeNumber="239"`` (the number Dijital Team actually uses). Can be
  blank for some employees (observed live) — callers must not assume it is
  always present.
"""

from pydantic import BaseModel


class BambooHREmployee(BaseModel):
    id: str
    employee_number: str | None = None
    first_name: str
    last_name: str
    display_name: str
    work_email: str
    birth_month: int
    birth_day: int
    department: str
    office_location: str
    employment_status: str
    hire_date: str | None = None  # ISO "YYYY-MM-DD"; None if genuinely missing
    termination_date: str | None = None  # ISO date; None if not terminated
