"""Real BambooHR employee-directory adapter. Field mapping verified
2026-08-14 against a real tenant (``dijitalteam`` subdomain, read-only
Custom Report calls only — no writes) — see
``docs/platform/bamboohr-live-discovery.md`` for the full survey. Mirrors
the config-gated `NotConfiguredError`-until-configured pattern already
used by ``app/integrations/graph_email/graph_client.py``.

Uses BambooHR's Custom Report API (``POST /v1/reports/custom?format=JSON``)
rather than the plain employee directory endpoint, so we can request
exactly the fields this service needs, including the derived MM-DD
``birthday`` field and ``hireDate``/``terminationDate``, none of which are
in the default directory payload.

Auth: HTTP Basic, username = API key, password = the literal string ``x``
(BambooHR's documented convention — the password field is ignored).

Never writes to BambooHR (CLAUDE.md §26/§58 — Lever/HubSpot integrations in
this repo are read-only for the same reason).
"""

from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.integrations.bamboohr.client import BambooHRClient, BambooHRFetchError, BambooHRNotConfiguredError
from app.integrations.bamboohr.schemas import BambooHREmployee

BAMBOOHR_BASE_URL_TEMPLATE = "https://api.bamboohr.com/api/gateway.php/{subdomain}/v1"

# Requested report fields. `status` is the single authoritative
# active/inactive field for this tenant (values: "Active" / "Inactive"),
# confirmed by live discovery — `employmentHistoryStatus` is deliberately
# NOT requested/used for filtering: it holds employment *type*
# (Full-Time/Part-Time/Contractor/Terminated), which is a different concept
# and would misclassify e.g. an active Contractor as filtered-out if used
# as a fallback.
_REPORT_FIELDS = [
    "id",
    "employeeNumber",
    "firstName",
    "lastName",
    "displayName",
    "workEmail",
    "department",
    "location",
    "birthday",
    "status",
    "hireDate",
    "terminationDate",
]


def _parse_birthday_field(raw: str | None) -> tuple[int, int] | None:
    """BambooHR's `birthday` report field is already ``MM-DD`` (no year —
    confirmed live, distinct from `dateOfBirth` which does carry a real
    year and is intentionally never requested here)."""
    if not raw:
        return None
    parts = raw.split("-")
    if len(parts) != 2:
        return None
    try:
        month, day = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return month, day


class BambooHRHttpClient(BambooHRClient):
    def __init__(self):
        settings = get_settings()
        if not (settings.bamboohr_api_key and settings.bamboohr_subdomain):
            raise BambooHRNotConfiguredError(
                "BambooHR is not configured — bamboohr_api_key and bamboohr_subdomain "
                "must both be set. Set INTEGRATIONS_MODE=mock to continue using "
                "MockBambooHRClient."
            )
        self._api_key = settings.bamboohr_api_key
        self._base_url = BAMBOOHR_BASE_URL_TEMPLATE.format(subdomain=settings.bamboohr_subdomain)

    def list_active_employees(self) -> list[BambooHREmployee]:
        try:
            response = httpx.post(
                f"{self._base_url}/reports/custom",
                params={"format": "JSON"},
                json={"fields": _REPORT_FIELDS},
                auth=(self._api_key, "x"),
                headers={"Accept": "application/json"},
                timeout=15.0,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001 - any network/auth/parse failure -> typed error
            raise BambooHRFetchError("Failed to fetch employee directory from BambooHR") from exc

        employees: list[BambooHREmployee] = []
        for row in payload.get("employees", []):
            status = (row.get("status") or "").strip()
            if status != "Active":
                continue  # server-side filtering — active only, never trust the caller to filter

            dob = _parse_birthday_field(row.get("birthday"))
            if dob is None:
                continue  # no usable birthday — cannot be scheduled, excluded rather than guessed
            birth_month, birth_day = dob

            employees.append(
                BambooHREmployee(
                    id=str(row.get("id", "")),
                    employee_number=(row.get("employeeNumber") or "").strip() or None,
                    first_name=row.get("firstName", "") or "",
                    last_name=row.get("lastName", "") or "",
                    display_name=row.get("displayName", "") or "",
                    work_email=row.get("workEmail", "") or "",
                    birth_month=birth_month,
                    birth_day=birth_day,
                    department=row.get("department", "") or "",
                    office_location=row.get("location", "") or "",
                    employment_status=status,
                    hire_date=row.get("hireDate") or None,
                    termination_date=row.get("terminationDate") or None,
                )
            )
        return employees

    def get_employee(self, employee_id: str) -> BambooHREmployee | None:
        """Fetches a single employee by BambooHR internal ``id``, active or
        not (used for the employee_number backfill against historical
        orders, which may reference an employee who has since left).

        BambooHR's Custom Report API does not offer a documented per-id
        filter for this tenant's setup, so this fetches the full report
        (same call ``list_active_employees`` makes, minus the active-only
        filter) and matches locally — acceptable for a one-off backfill
        script, not used on any hot path."""
        try:
            response = httpx.post(
                f"{self._base_url}/reports/custom",
                params={"format": "JSON"},
                json={"fields": _REPORT_FIELDS},
                auth=(self._api_key, "x"),
                headers={"Accept": "application/json"},
                timeout=15.0,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            raise BambooHRFetchError(f"Failed to fetch employee {employee_id} from BambooHR") from exc

        for row in payload.get("employees", []):
            if str(row.get("id", "")) != employee_id:
                continue
            dob = _parse_birthday_field(row.get("birthday"))
            birth_month, birth_day = dob if dob else (1, 1)
            return BambooHREmployee(
                id=str(row.get("id", "")),
                employee_number=(row.get("employeeNumber") or "").strip() or None,
                first_name=row.get("firstName", "") or "",
                last_name=row.get("lastName", "") or "",
                display_name=row.get("displayName", "") or "",
                work_email=row.get("workEmail", "") or "",
                birth_month=birth_month,
                birth_day=birth_day,
                department=row.get("department", "") or "",
                office_location=row.get("location", "") or "",
                employment_status=(row.get("status") or "").strip(),
                hire_date=row.get("hireDate") or None,
                termination_date=row.get("terminationDate") or None,
            )
        return None
