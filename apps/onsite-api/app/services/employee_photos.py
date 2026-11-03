"""Employee profile photos for Diji On-site, via people-api's Workforce
Directory photo proxy (BambooHR ``photoUrl`` — the same source Customer
Portal V2 uses). No Microsoft Graph call, no new credential: people-api is
the only BambooHR caller and onsite-api uses its existing internal token.

Identity mapping: attendance EmpCode → exactly one Workforce Directory entry
by Employee Number (the same exact-match rule as everywhere else) → that
entry's ``bamboohr_id``. Ambiguous or unmatched codes get no photo; names are
never used to guess.

Efficiency (dashboards refresh every 30 s; photos must not follow):
- bounded in-process LRU cache: hits 24 h, "no photo" 6 h, throttling for
  the source's Retry-After;
- single-flight per employee: concurrent requests for one photo share one
  upstream call;
- at most ``MAX_CONCURRENT`` upstream photo calls at once per replica;
- the browser additionally caches each image (private, 24 h) and only asks
  for photos of rows it is rendering.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

import httpx

from app.services import workforce_directory

logger = logging.getLogger("onsite-api.photos")

HIT_TTL = 24 * 3600
MISS_TTL = 6 * 3600
MAX_ENTRIES = 3000
MAX_CONCURRENT = 4


@dataclass(frozen=True)
class Photo:
    content: bytes
    content_type: str


class _Entry:
    __slots__ = ("photo", "expires")

    def __init__(self, photo: Photo | None, ttl: float):
        self.photo = photo
        self.expires = time.monotonic() + ttl


class PhotoCache:
    def __init__(self, fetch=None, max_entries: int = MAX_ENTRIES, max_concurrent: int = MAX_CONCURRENT):
        self._fetch = fetch or _fetch_upstream
        self._max = max_entries
        self._data: OrderedDict[str, _Entry] = OrderedDict()
        self._lock = threading.Lock()
        self._inflight: dict[str, threading.Lock] = {}
        self._slots = threading.BoundedSemaphore(max_concurrent)
        self.upstream_calls = 0

    def _cached(self, key: str) -> _Entry | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            if entry.expires < time.monotonic():
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return entry

    def _store(self, key: str, photo: Photo | None, ttl: float) -> None:
        with self._lock:
            self._data[key] = _Entry(photo, ttl)
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def get(self, bamboohr_id: str) -> Photo | None:
        if (hit := self._cached(bamboohr_id)) is not None:
            return hit.photo
        with self._lock:
            flight = self._inflight.setdefault(bamboohr_id, threading.Lock())
        with flight:  # single-flight: followers wait for the leader's result
            if (hit := self._cached(bamboohr_id)) is not None:
                return hit.photo
            with self._slots:
                self.upstream_calls += 1
                photo, ttl = self._fetch(bamboohr_id)
            self._store(bamboohr_id, photo, ttl)
        with self._lock:
            self._inflight.pop(bamboohr_id, None)
        return photo

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self.upstream_calls = 0


def _fetch_upstream(bamboohr_id: str) -> tuple[Photo | None, float]:
    """(photo or None, cache seconds). Never raises."""
    client = workforce_directory._client()
    if client is None:
        return None, 300
    try:
        resp = client.get_photo(bamboohr_id)
    except httpx.HTTPError as exc:
        logger.info("photo fetch failed for an employee: %s", exc.__class__.__name__)
        return None, 120
    if resp.status_code == 200 and resp.content:
        return Photo(resp.content, resp.headers.get("content-type", "image/jpeg").split(";")[0]), HIT_TTL
    if resp.status_code in (429, 503):
        try:
            retry = float(resp.headers.get("Retry-After", "60"))
        except ValueError:
            retry = 60
        return None, max(5.0, min(retry, 3600.0))
    if resp.status_code == 404:
        return None, MISS_TTL
    return None, 300  # auth/other failures: initials for a while, then retry


cache = PhotoCache()


def bamboohr_id_for(code: str) -> str | None:
    """The single directory entry for this exact Employee Number that has a
    photo — or None (unmatched, ambiguous, no photo, directory unavailable)."""
    directory = workforce_directory.load()
    if not directory.available:
        return None
    matches = directory.by_employee_number().get(code, [])
    if len(matches) != 1 or not matches[0].get("has_photo") or not matches[0].get("bamboohr_id"):
        return None
    return str(matches[0]["bamboohr_id"])


def photo_for(code: str) -> Photo | None:
    bid = bamboohr_id_for(code)
    return cache.get(bid) if bid else None
