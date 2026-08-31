"""Typed HTTP client for the Recruitment Source domain (recruitment-api).

The one way a DijiOne application consumes Lever data (Architecture
Completion Plan §3). Mirrors ``PlatformClient``: an optional injected
``httpx.Client`` for in-process tests, ``X-Internal-Token`` +
``X-Internal-Caller`` on every request, an explicit per-method timeout.

Read methods RAISE ``httpx.HTTPError`` on failure — the caller decides
whether to degrade (e.g. serve a last-good local projection) rather than
this client silently returning empty data and hiding a source outage.
"""

from __future__ import annotations

import httpx


class RecruitmentSourceClient:
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

    # --- reads (raise on failure) ------------------------------------

    def list_postings(self, *, include_archived: bool = True) -> list[dict]:
        return self._get(
            "/api/recruitment/postings", params={"include_archived": include_archived}
        ).json()

    def get_posting(self, external_id: str) -> dict | None:
        resp = self._request("GET", f"/api/recruitment/postings/{external_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def list_candidacies(
        self, *, posting_external_id: str | None = None, limit: int = 200
    ) -> list[dict]:
        params: dict = {"limit": limit}
        if posting_external_id is not None:
            params["posting_external_id"] = posting_external_id
        return self._get("/api/recruitment/candidacies", params=params).json()

    def get_freshness(self) -> dict:
        return self._get("/api/recruitment/freshness").json()

    def get_sync_run(self, run_id: str) -> dict:
        return self._get(f"/api/recruitment/sync/{run_id}").json()

    def list_sync_history(self, limit: int = 20) -> list[dict]:
        return self._get("/api/recruitment/sync/history", params={"limit": limit}).json()

    # --- ad-hoc sync (async 202) -----------------------------------

    def request_sync(
        self, *, requested_by_user_id: int | None = None,
        requested_by_application: str = "talent-flow",
    ) -> dict:
        resp = self._request(
            "POST",
            "/api/recruitment/internal/sync",
            json={
                "requested_by_application": requested_by_application,
                "requested_by_user_id": requested_by_user_id,
            },
        )
        resp.raise_for_status()
        return resp.json()

    # --- internals -------------------------------------------------

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
