"""Real EmployeeSourceClient — calls people-api over
``auth_client_py.EmployeeDirectoryClient``. birthday-api never talks to
BambooHR directly (Architecture Completion Plan §3).
"""

from __future__ import annotations

import httpx
from auth_client_py import EmployeeDirectoryClient

from app.core.config import get_settings
from app.integrations.people_source.client import EmployeeSourceClient, EmployeeSourceUnavailableError
from app.integrations.people_source.schemas import EmployeeRecord


def _to_record(row: dict) -> EmployeeRecord:
    return EmployeeRecord(
        id=row["bamboohr_id"], employee_number=row.get("employee_number"),
        display_name=row["full_name"], work_email=row["work_email"],
        birth_month=row["birth_month"], birth_day=row["birth_day"],
        department=row.get("department") or "", office_location=row["office_location"],
        employment_status=row["employment_status"], hire_date=row.get("hire_date"),
        termination_date=row.get("termination_date"), address_line1=row.get("address_line1"),
        address_line2=row.get("address_line2"), city=row.get("city"),
        state_province=row.get("state_province"), postal_code=row.get("postal_code"),
        country=row.get("country"),
    )


class PeopleApiEmployeeSource(EmployeeSourceClient):
    def __init__(self) -> None:
        settings = get_settings()
        self._client = EmployeeDirectoryClient(
            base_url=settings.people_api_url,
            internal_secret=settings.internal_service_secret,
            timeout=5.0,
            caller="birthday-api",
        )

    def list_active_employees(self) -> list[EmployeeRecord]:
        try:
            rows = self._client.list_employees(active_only=True)
        except httpx.HTTPError as exc:
            raise EmployeeSourceUnavailableError(
                "people-api unreachable — employee directory sync deferred"
            ) from exc
        return [_to_record(r) for r in rows]

    def get_employee(self, employee_id: str) -> EmployeeRecord | None:
        try:
            row = self._client.get_employee(employee_id)
        except httpx.HTTPError as exc:
            raise EmployeeSourceUnavailableError(
                f"people-api unreachable — could not look up employee {employee_id}"
            ) from exc
        return _to_record(row) if row is not None else None
