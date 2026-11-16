"""Session revocation, enforced locally from a cached snapshot.

``platform-api`` keeps a per-user ``access_version`` and publishes a small snapshot of
it (``GET /api/platform/internal/access-versions``). Every API that verifies session
tokens holds the latest snapshot in memory and rejects a token when its user is
inactive or the token's ``av`` claim is older than the user's current version. There is
no per-request call to ``platform-api``: a background thread refreshes the snapshot.

Known revocations are never forgotten: the last good snapshot is kept for the life of
the process, whatever happens to the feed. What ageing affects is how far the snapshot
can be trusted to be COMPLETE:

    FRESH       refreshed within ``fresh_seconds``                       -> normal
    STALE       older than that, within ``restricted_seconds``           -> SENSITIVE routes refused
    RESTRICTED  never loaded (cold start) or older than                  -> only READ and OWN routes
                ``restricted_seconds``                                    served

What a route may do is decided by an explicit per-service policy (``register_route_policy``),
never by its HTTP method alone: a GET can change state, and a POST can be harmless.

    READ       reads that expose nothing sensitive            served in every state
    OWN        a person recording or withdrawing their own    served in every state
               data (clocking in, withdrawing a request)
    WRITE      ordinary changes                               refused when RESTRICTED
    SENSITIVE  anything administrative, approving, sending    served only when FRESH
               outside, exporting, or exposing personal data
               in bulk
    EXEMPT     does not authenticate a user (health, public)  not subject to revocation

A route missing from a registered policy is treated as SENSITIVE.

Revocations are created only by platform-api, so while it is down none can appear that a
replica has not already seen (apart from the last refresh interval).

Disabled unless ``REVOCATION_ENABLED`` is true, so the library can ship ahead of the
platform change and be switched on per environment.
"""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

logger = logging.getLogger("dijione.revocation")

FRESH = "FRESH"
STALE = "STALE"
RESTRICTED = "RESTRICTED"

FEED_PATH = "/api/platform/internal/access-versions"

READ = "READ"
OWN = "OWN"
WRITE = "WRITE"
SENSITIVE = "SENSITIVE"
EXEMPT = "EXEMPT"
ROUTE_CLASSES = frozenset({READ, OWN, WRITE, SENSITIVE, EXEMPT})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

_route_policy: dict[str, str] | None = None


def register_route_policy(policy: dict[str, str]) -> None:
    """Install this service's route policy: ``"METHOD /path/{template}"`` -> class."""
    unknown = set(policy.values()) - ROUTE_CLASSES
    if unknown:
        raise ValueError(f"unknown route classes: {sorted(unknown)}")
    global _route_policy
    _route_policy = dict(policy)


def route_class(method: str, route_path: str | None) -> str:
    """The class of a route. With no policy registered a service falls back to the HTTP
    method (reads READ, everything else WRITE); with one, an unlisted route is SENSITIVE."""
    method = "GET" if method == "HEAD" else method
    if _route_policy is None:
        return READ if method in SAFE_METHODS else WRITE
    return _route_policy.get(f"{method} {route_path}", SENSITIVE)

# fetch(etag) -> (status, etag, users). ``users`` maps user id -> (access_version, active)
# on a 200 and is None on a 304.
Fetch = Callable[[str | None], tuple[int, str | None, dict[int, tuple[int, bool]] | None]]


@dataclass(frozen=True)
class _Snapshot:
    users: dict[int, tuple[int, bool]]
    etag: str | None
    fetched_at: float  # monotonic seconds of the last successful 200 or 304


class RevocationGuard:
    def __init__(
        self,
        fetch: Fetch,
        *,
        refresh_seconds: float = 30.0,
        fresh_seconds: float = 300.0,
        restricted_seconds: float = 3600.0,
        max_backoff_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._fetch = fetch
        self.refresh_seconds = refresh_seconds
        self.fresh_seconds = fresh_seconds
        self.restricted_seconds = restricted_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self._clock = clock
        self._snapshot: _Snapshot | None = None
        self._failures = 0
        self._last_state: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # --- snapshot ---------------------------------------------------------------

    def refresh_once(self) -> bool:
        """One refresh. On any failure the previous snapshot is kept untouched."""
        current = self._snapshot
        try:
            status, etag, users = self._fetch(current.etag if current else None)
        except Exception as exc:  # noqa: BLE001 - any failure leaves the snapshot as it was
            self._failures += 1
            logger.warning("revocation feed unavailable (%s): %s", type(exc).__name__, exc)
            self._note_state()
            return False
        now = self._clock()
        if status == 304 and current is not None:
            self._snapshot = _Snapshot(current.users, current.etag, now)
        elif status == 200 and users is not None:
            self._snapshot = _Snapshot(self._merge(current.users if current else {}, users), etag, now)
        else:
            self._failures += 1
            logger.warning("revocation feed returned an unusable response (status %s)", status)
            self._note_state()
            return False
        self._failures = 0
        self._note_state()
        return True

    @staticmethod
    def _merge(known: dict[int, tuple[int, bool]], incoming: dict[int, tuple[int, bool]]) -> dict[int, tuple[int, bool]]:
        """Fold a new snapshot into what is known, never going backwards.

        A user's version only ever rises, and every change to an account's status raises it,
        so an entry is accepted only if its version is higher, or the same with the same
        status. An older or truncated snapshot (a database restored from backup, a lagging
        replica) therefore cannot lower a version, reactivate an inactive account, or make
        a known revocation disappear."""
        merged = dict(known)
        for user_id, entry in incoming.items():
            old = merged.get(user_id)
            if old is None or entry[0] > old[0] or (entry[0] == old[0] and entry[1] == old[1]):
                merged[user_id] = entry
            else:
                logger.warning("revocation snapshot entry for user %s ignored: it would move backwards", user_id)
        return merged

    def age_seconds(self) -> float | None:
        snap = self._snapshot
        return None if snap is None else max(0.0, self._clock() - snap.fetched_at)

    def state(self) -> str:
        age = self.age_seconds()
        if age is None or age > self.restricted_seconds:
            return RESTRICTED
        return FRESH if age <= self.fresh_seconds else STALE

    def _note_state(self) -> None:
        state = self.state()
        if state != self._last_state:
            logger.warning("revocation state %s -> %s", self._last_state, state)
            self._last_state = state

    # --- decisions --------------------------------------------------------------

    def is_revoked(self, user_id: int, token_version: int) -> bool:
        """True when the user is inactive or the token predates their current version.
        Answers from whatever snapshot is held, however old."""
        snap = self._snapshot
        if snap is None:
            return False
        entry = snap.users.get(user_id)
        if entry is None:
            return False
        version, active = entry
        return (not active) or token_version < version

    def status(self) -> dict:
        age = self.age_seconds()
        return {
            "enabled": True,
            "state": self.state(),
            "snapshot_age_seconds": None if age is None else round(age, 1),
            "known_users": 0 if self._snapshot is None else len(self._snapshot.users),
            "consecutive_failures": self._failures,
        }

    # --- background refresh -----------------------------------------------------

    def start(self) -> None:
        """Load a snapshot now (so a normal start is FRESH before serving), then keep it
        current in a daemon thread."""
        if self._thread is not None:
            return
        self.refresh_once()
        self._thread = threading.Thread(target=self._loop, name="revocation-refresh", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _next_delay(self) -> float:
        base = self.refresh_seconds * (2 ** min(self._failures, 6)) if self._failures else self.refresh_seconds
        return min(base, max(self.max_backoff_seconds, self.refresh_seconds)) * random.uniform(0.85, 1.15)

    def _loop(self) -> None:
        while not self._stop.wait(self._next_delay()):
            self.refresh_once()


# --- process-wide guard, configured from the environment ---------------------------

_guard: RevocationGuard | None = None
_configured = False
_lock = threading.Lock()


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def http_fetch(base_url: str, internal_secret: str, timeout: float = 3.0) -> Fetch:
    url = base_url.rstrip("/") + FEED_PATH

    def fetch(etag: str | None):
        headers = {"X-Internal-Token": internal_secret, "X-Internal-Caller": "revocation-guard"}
        if etag:
            headers["If-None-Match"] = etag
        resp = httpx.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 304:
            return 304, etag, None
        if resp.status_code != 200:
            return resp.status_code, None, None
        users = {int(uid): (int(v["av"]), bool(v["active"])) for uid, v in resp.json().get("users", {}).items()}
        return 200, resp.headers.get("etag"), users

    return fetch


def get_guard() -> RevocationGuard | None:
    """The process-wide guard, created on first use from ``REVOCATION_ENABLED``,
    ``PLATFORM_API_URL`` and ``INTERNAL_SERVICE_SECRET``; ``None`` when disabled."""
    global _guard, _configured
    if _configured:
        return _guard
    with _lock:
        if _configured:
            return _guard
        if _truthy(os.environ.get("REVOCATION_ENABLED")):
            url = os.environ.get("PLATFORM_API_URL", "")
            secret = os.environ.get("INTERNAL_SERVICE_SECRET", "")
            if not url or not secret:
                raise RuntimeError("REVOCATION_ENABLED needs PLATFORM_API_URL and INTERNAL_SERVICE_SECRET")
            guard = RevocationGuard(
                http_fetch(url, secret),
                refresh_seconds=float(os.environ.get("REVOCATION_REFRESH_SECONDS", "30")),
                fresh_seconds=float(os.environ.get("REVOCATION_FRESH_SECONDS", "300")),
                restricted_seconds=float(os.environ.get("REVOCATION_RESTRICTED_SECONDS", "3600")),
            )
            guard.start()
            _guard = guard
        _configured = True
        return _guard


def set_guard(guard: RevocationGuard | None) -> None:
    """Install (or clear) the process-wide guard. For tests and explicit wiring."""
    global _guard, _configured
    with _lock:
        _guard, _configured = guard, True


def revocation_status() -> dict:
    """For a service's deep health check."""
    guard = get_guard()
    return {"enabled": False} if guard is None else guard.status()
