"""Typed HTTP client for the People / Workforce domain (people-api).

The one way a DijiOne application consumes BambooHR employee data
(Architecture Completion Plan §3). Mirrors ``RecruitmentSourceClient``:
``X-Internal-Token`` + ``X-Internal-Caller`` on every request, an optional
injected ``httpx.Client`` for in-process tests.

Read methods RAISE ``httpx.HTTPError`` on failure — the caller decides how
to degrade (e.g. defer detection and self-heal next cycle) rather than this
client silently returning empty data and hiding a source outage.
"""

from __future__ import annotations

import httpx


class EmployeeDirectoryClient:
    def __init__(
        self,
        base_url: str,
        internal_secret: str,
        timeout: float = 5.0,
        *,
        client: httpx.Client | None = None,
        caller: str | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._internal_secret = internal_secret
        self._timeout = timeout
        self._client = client
        self._caller = caller

    def list_employees(self, *, active_only: bool = True) -> list[dict]:
        return self._get("/api/people/employees", params={"active_only": active_only}).json()

    def get_employee(self, bamboohr_id: str) -> dict | None:
        """Single-employee lookup — used by historical tooling (e.g. a
        terminated employee referenced by an old order), not the daily
        scan. Requests the ``include_inactive_live_lookup`` escape hatch so
        an employee no longer in the active-only read model still resolves
        via a single live, read-only BambooHR GET on people-api's side."""
        resp = self._request(
            "GET", f"/api/people/employees/{bamboohr_id}",
            params={"include_inactive_live_lookup": True},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def get_freshness(self) -> dict:
        return self._get("/api/people/freshness").json()

    def request_sync(
        self, *, requested_by_user_id: int | None = None, requested_by_application: str = "birthday"
    ) -> dict:
        resp = self._request(
            "POST", "/api/people/internal/sync",
            json={
                "requested_by_application": requested_by_application,
                "requested_by_user_id": requested_by_user_id,
            },
        )
        resp.raise_for_status()
        return resp.json()

    def _get(self, path: str, *, params: dict | None = None) -> httpx.Response:
        resp = self._request("GET", path, params=params)
        resp.raise_for_status()
        return resp

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = {"X-Internal-Token": self._internal_secret}
        if self._caller:
            headers["X-Internal-Caller"] = self._caller
        kwargs["headers"] = {**headers, **kwargs.get("headers", {})}
        if self._client is not None:
            return self._client.request(method, path, **kwargs)
        return httpx.request(method, f"{self._base_url}{path}", timeout=self._timeout, **kwargs)
