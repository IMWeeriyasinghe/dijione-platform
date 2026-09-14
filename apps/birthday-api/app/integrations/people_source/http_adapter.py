"""Real EmployeeSourceClient — calls people-api over
``auth_client_py.EmployeeDirectoryClient``. birthday-api never talks to
BambooHR directly (Architecture Completion Plan §3).
"""

from __future__ import annotations

import time

import httpx
from auth_client_py import EmployeeDirectoryClient

from app.core.config import get_settings
from app.integrations.people_source.client import EmployeeSourceClient, EmployeeSourceUnavailableError
from app.integrations.people_source.schemas import EmployeeRecord

# One bounded retry after a short delay (Phase 1.6 §9) — absorbs a
# transient cold-start miss (people-api minReplicas=0) within the same scan
# run instead of deferring the whole day for it. Not a general backoff
# loop: a genuine outage still defers, just one retry later.
_RETRY_DELAY_SECONDS = 3.0


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
            timeout=settings.people_api_timeout_seconds,
            caller="birthday-api",
        )

    def list_active_employees(self) -> list[EmployeeRecord]:
        """The daily scan's one upfront availability check
        (``detection_service.run_daily_scan``) — retried once (Phase 1.6
        §9) so a cold-start miss on the first attempt doesn't defer the
        whole day's scan by itself."""
        try:
            rows = self._client.list_employees(active_only=True)
        except httpx.HTTPError:
            time.sleep(_RETRY_DELAY_SECONDS)
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

    # --- People-source freshness / ad-hoc refresh (Phase 1.5 §B) --------
    # Thin passthroughs to auth_client_py.EmployeeDirectoryClient — the
    # daily people-sync-job is the primary refresh; these back the
    # "last refreshed / Refresh now" affordance in birthday-web.

    def freshness(self) -> dict:
        try:
            return self._client.get_freshness()
        except httpx.HTTPError as exc:
            raise EmployeeSourceUnavailableError("people-api unreachable — freshness unknown") from exc

    def request_sync(self, *, requested_by_user_id: int | None = None) -> dict:
        try:
            return self._client.request_sync(
                requested_by_user_id=requested_by_user_id, requested_by_application="birthday"
            )
        except httpx.HTTPError as exc:
            raise EmployeeSourceUnavailableError("people-api unreachable — sync not requested") from exc
