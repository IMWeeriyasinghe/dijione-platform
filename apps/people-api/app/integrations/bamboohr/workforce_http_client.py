"""Real BambooHR adapter for the generic Workforce Directory.

Same read-only Custom Report API (``POST /v1/reports/custom?format=JSON``)
and auth convention as ``http_client.BambooHRHttpClient``, but with its own
minimal field list and **no** status or birthday filtering: workforce
consumers need the full roster to resolve historical identifiers. Never
requests birthday, address, email, phone or compensation fields.
Never writes to BambooHR.
"""

from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.integrations.bamboohr.workforce_client import (
    BambooHRWorkforceClient,
    WorkforceSourceFetchError,
    WorkforceSourceNotConfiguredError,
)
from app.integrations.bamboohr.workforce_schemas import BambooHRWorkforceRecord

_WORKFORCE_REPORT_FIELDS = [
    "id",
    "employeeNumber",
    "displayName",
    "firstName",
    "lastName",
    "department",
    "jobTitle",
    "location",
    "status",
    "hireDate",
    "terminationDate",
]


def _employee_number(raw) -> str | None:
    """Kept verbatim (no trim, no zero-stripping, no cast) — only a missing
    or whitespace-only value is treated as blank."""
    if raw is None:
        return None
    value = str(raw)
    return value if value.strip() else None


class BambooHRWorkforceHttpClient(BambooHRWorkforceClient):
    def __init__(self):
        settings = get_settings()
        if not (settings.bamboohr_api_key and settings.bamboohr_subdomain):
            raise WorkforceSourceNotConfiguredError(
                "BambooHR is not configured — bamboohr_api_key and bamboohr_subdomain "
                "must both be set. Set INTEGRATIONS_MODE=mock to continue using "
                "MockBambooHRWorkforceClient."
            )
        self._api_key = settings.bamboohr_api_key
        self._base_url = settings.bamboohr_base_url_template.format(subdomain=settings.bamboohr_subdomain)

    def list_workforce_records(self) -> list[BambooHRWorkforceRecord]:
        try:
            response = httpx.post(
                f"{self._base_url}/reports/custom",
                params={"format": "JSON"},
                json={"fields": _WORKFORCE_REPORT_FIELDS},
                auth=(self._api_key, "x"),
                headers={"Accept": "application/json"},
                timeout=15.0,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001 - any network/auth/parse failure -> typed error
            raise WorkforceSourceFetchError("Failed to fetch workforce directory from BambooHR") from exc

        records: list[BambooHRWorkforceRecord] = []
        for row in payload.get("employees", []):
            record_id = str(row.get("id") or "")
            if not record_id:
                continue  # no stable key — cannot be reconciled
            first_last = f"{row.get('firstName') or ''} {row.get('lastName') or ''}".strip()
            records.append(
                BambooHRWorkforceRecord(
                    id=record_id,
                    employee_number=_employee_number(row.get("employeeNumber")),
                    display_name=(row.get("displayName") or "").strip() or first_last,
                    department=row.get("department") or "",
                    job_title=row.get("jobTitle") or "",
                    location=row.get("location") or "",
                    employment_status=(row.get("status") or "").strip(),
                    hire_date=row.get("hireDate") or None,
                    termination_date=row.get("terminationDate") or None,
                )
            )
        return records
