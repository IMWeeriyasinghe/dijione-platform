"""The one best-effort call admin-api still makes to talent-api: the live
pending-talent-request count for the dashboard. Client display names now
come from Platform Core, which owns canonical Client identity (Architecture
Completion Plan §6.1). A talent-api outage degrades the pending count to
zero instead of breaking user/role administration (CR §38, §39).
"""

from __future__ import annotations

import logging

import httpx
from auth_client_py import PlatformClient

from app.core.config import get_settings

logger = logging.getLogger("dijione.admin_api.talent_gateway")


def get_talent_client() -> PlatformClient:
    settings = get_settings()
    return PlatformClient(
        base_url=settings.talent_api_url,
        internal_secret=settings.internal_service_secret,
        caller="admin-api",
    )


def pending_talent_requests(client: PlatformClient) -> int:
    try:
        resp = client.get_internal("/api/talent/summary")
        return int(resp.json().get("pending_requests", 0))
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logger.warning("talent-api summary unavailable (non-fatal): %s", exc)
        return 0
