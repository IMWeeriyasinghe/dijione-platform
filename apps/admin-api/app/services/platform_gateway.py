"""Thin pass-through to Platform Core's ``/api/platform/admin/*`` surface.

admin-api owns no database — every mutation and read here is a live forward
of the caller's own request, re-authorized by Platform Core against the
caller's *own* bearer token (CR §48). A Platform Core outage surfaces as a
503 to the browser (this is a live user-facing admin action, not a
background side effect that can fail silently — contrast with
``talent_gateway``'s best-effort enrichment calls).
"""

from __future__ import annotations

import httpx
from auth_client_py import PlatformClient
from fastapi import HTTPException, status

from app.core.config import get_settings


def get_platform_client() -> PlatformClient:
    settings = get_settings()
    return PlatformClient(
        base_url=settings.platform_api_url,
        internal_secret=settings.internal_service_secret,
        caller="admin-api",
    )


def raise_for_platform_error(resp: httpx.Response) -> None:
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail)


def call_platform_admin(
    client: PlatformClient,
    method: str,
    path: str,
    *,
    bearer_token: str,
    json: dict | None = None,
    params: dict | None = None,
) -> dict:
    try:
        resp = client.request_admin(method, path, bearer_token=bearer_token, json=json, params=params)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"Platform Core is unavailable: {exc}"
        ) from exc
    raise_for_platform_error(resp)
    return resp.json()
