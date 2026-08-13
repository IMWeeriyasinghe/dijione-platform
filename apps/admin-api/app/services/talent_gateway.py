"""Best-effort enrichment calls to talent-api — client display names for the
Admin Center's client-scope picker, and the live pending-request count for
the dashboard. Both are read-only "nice to have" presentation data, so a
talent-api outage degrades the Admin Center gracefully (empty names, zero
count) instead of breaking user/role administration, which has nothing to
do with DijiTalentFlow (CR §38, §39).
"""

from __future__ import annotations

import logging

import httpx
from auth_client_py import PlatformClient

from app.core.config import get_settings

logger = logging.getLogger("dijione.admin_api.talent_gateway")


def get_talent_client() -> PlatformClient:
    settings = get_settings()
    return PlatformClient(base_url=settings.talent_api_url, internal_secret=settings.internal_service_secret)


def client_names_map(client: PlatformClient) -> dict[int, str]:
    try:
        resp = client.get_internal("/api/talent/internal/clients-lite")
        return {row["id"]: row["name"] for row in resp.json()}
    except httpx.HTTPError as exc:
        logger.warning("talent-api clients-lite unavailable (non-fatal): %s", exc)
        return {}


def clients_lite_list(client: PlatformClient) -> list[dict]:
    try:
        resp = client.get_internal("/api/talent/internal/clients-lite")
        return resp.json()
    except httpx.HTTPError as exc:
        logger.warning("talent-api clients-lite unavailable (non-fatal): %s", exc)
        return []


def pending_talent_requests(client: PlatformClient) -> int:
    try:
        resp = client.get_internal("/api/talent/summary")
        return int(resp.json().get("pending_requests", 0))
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logger.warning("talent-api summary unavailable (non-fatal): %s", exc)
        return 0
