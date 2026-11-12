"""Employee identity for On-site — consumed ONLY through people-api's
published Workforce Directory contract (``auth_client_py.WorkforceDirectoryClient``).
Never the People database.

Degrades gracefully: if ``PEOPLE_API_URL`` is unset or people-api is
unreachable, ``load()`` returns ``available=False`` and On-site keeps
working with raw EmpCodes only.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

import httpx
from auth_client_py import WorkforceDirectoryClient

from app.core.config import get_settings

logger = logging.getLogger("onsite-api.workforce")

_lock = threading.Lock()
_cache: dict[str, object] = {"at": 0.0, "snapshot": None}


@dataclass(frozen=True)
class DirectorySnapshot:
    available: bool
    entries: list[dict] = field(default_factory=list)

    def by_employee_number(self) -> dict[str, list[dict]]:
        """Exact, case-sensitive string key — no trimming, no zero-stripping,
        no numeric cast. Blank/None numbers are never keys."""
        out: dict[str, list[dict]] = {}
        for e in self.entries:
            number = e.get("employee_number")
            if number is None or not str(number).strip():
                continue
            out.setdefault(number, []).append(e)
        return out


def _client() -> WorkforceDirectoryClient | None:
    settings = get_settings()
    if not settings.people_api_url:
        return None
    return WorkforceDirectoryClient(
        base_url=settings.people_api_url, internal_secret=settings.internal_service_secret,
        timeout=settings.people_api_timeout_seconds, caller="onsite-api",
    )


def load(*, force: bool = False) -> DirectorySnapshot:
    ttl = get_settings().workforce_cache_ttl_seconds
    with _lock:
        cached = _cache["snapshot"]
        if not force and cached is not None and cached.available and time.monotonic() - _cache["at"] < ttl:
            return cached
    client = _client()
    if client is None:
        return DirectorySnapshot(available=False)
    try:
        snapshot = DirectorySnapshot(available=True, entries=client.list_entries(status="all"))
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("workforce directory unavailable: %s", exc.__class__.__name__)
        return DirectorySnapshot(available=False)
    with _lock:
        _cache["snapshot"], _cache["at"] = snapshot, time.monotonic()
    return snapshot


def clear_cache() -> None:
    with _lock:
        _cache["snapshot"], _cache["at"] = None, 0.0
