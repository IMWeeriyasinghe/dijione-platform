"""The one best-effort call admin-api still makes to talent-api: the live
pending-talent-request count for the dashboard. Client display names now
come from Platform Core, which owns canonical Client identity (Architecture
Completion Plan §6.1). A talent-api outage degrades the pending count to
zero instead of breaking user/role administration (CR §38, §39).

The dashboard starts this count in parallel with its Platform Core call and
waits at most ``TALENT_SUMMARY_BUDGET_SECONDS`` for it, so a slow talent-api
can never hold the Admin dashboard open.
"""

from __future__ import annotations

import contextvars
import logging
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

import httpx
from auth_client_py import PlatformClient

from app.core.config import get_settings

logger = logging.getLogger("dijione.admin_api.talent_gateway")

# The pending count is a nice-to-have figure; the dashboard never waits longer than this for it.
TALENT_SUMMARY_BUDGET_SECONDS = 3.0

# Small and bounded: one short-lived task per dashboard request.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="admin-dashboard-talent")


def get_talent_client() -> PlatformClient:
    settings = get_settings()
    return PlatformClient(
        base_url=settings.talent_api_url,
        internal_secret=settings.internal_service_secret,
        timeout=TALENT_SUMMARY_BUDGET_SECONDS,
        caller="admin-api",
    )


def pending_talent_requests(client: PlatformClient) -> int:
    try:
        resp = client.get_internal("/api/talent/summary")
        return int(resp.json().get("pending_requests", 0))
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logger.warning("talent-api summary unavailable (non-fatal): %s", exc)
        return 0


def start_pending_talent_requests(client: PlatformClient) -> Future[int]:
    """Begin the count in the background (carrying the request's correlation id)."""
    context = contextvars.copy_context()
    return _executor.submit(context.run, pending_talent_requests, client)


def pending_talent_requests_within_budget(pending: Future[int]) -> int:
    try:
        return pending.result(timeout=TALENT_SUMMARY_BUDGET_SECONDS)
    except FutureTimeout:
        logger.warning("talent-api summary exceeded %.1fs (non-fatal); showing 0", TALENT_SUMMARY_BUDGET_SECONDS)
        return 0
