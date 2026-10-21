"""HTTP client for people-api's generic Workforce Directory contract
(``docs/platform/workforce-directory.md``). Separate from
``EmployeeDirectoryClient`` (the Birthday-oriented Employee contract).
Internal-token authenticated; consumers never read the People database."""

from __future__ import annotations

import httpx


class WorkforceDirectoryClient:
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

    def list_entries(self, *, status: str = "all") -> list[dict]:
        """``status`` is ``all`` (default), ``active`` or ``inactive``."""
        return self._get("/api/people/workforce-directory", params={"status": status}).json()

    def get_freshness(self) -> dict:
        return self._get("/api/people/workforce-directory/freshness").json()

    def request_sync(self, *, requested_by_application: str, requested_by_user_id: int | None = None) -> dict:
        resp = self._request(
            "POST", "/api/people/internal/workforce-directory/sync",
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
        from auth_client_py.correlation import CORRELATION_HEADER, get_correlation_id

        headers = {"X-Internal-Token": self._internal_secret}
        if self._caller:
            headers["X-Internal-Caller"] = self._caller
        cid = get_correlation_id()
        if cid:
            headers[CORRELATION_HEADER] = cid
        kwargs["headers"] = {**headers, **kwargs.get("headers", {})}
        if self._client is not None:
            return self._client.request(method, path, **kwargs)
        return httpx.request(method, f"{self._base_url}{path}", timeout=self._timeout, **kwargs)
