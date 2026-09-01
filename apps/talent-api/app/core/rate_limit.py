"""A minimal in-process fixed-window rate limiter for the unauthenticated
magic-link redeem endpoint (plan B.12).

Deliberately not a distributed limiter — that is future hardening, not V1.
Its job here is to blunt brute-force / enumeration against `/redeem`
(already infeasible against a 256-bit token, this is defence in depth) and
to keep one noisy source from monopolising the endpoint. Per-source-IP and
a global ceiling, both fixed 60s windows.

Sync FastAPI routes run in a threadpool, so every counter mutation is under
one lock.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class _Window:
    count: int = 0
    reset_at: float = 0.0


@dataclass
class FixedWindowRateLimiter:
    per_key_limit: int
    global_limit: int
    window_seconds: float = 60.0
    _keys: dict[str, _Window] = field(default_factory=dict)
    _global: _Window = field(default_factory=_Window)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _bump(self, window: _Window, limit: int, now: float) -> bool:
        if now >= window.reset_at:
            window.count = 0
            window.reset_at = now + self.window_seconds
        window.count += 1
        return window.count <= limit

    def allow(self, key: str) -> bool:
        """True if this call is within both the per-key and global limits.
        Counts the call regardless (a rejected call still consumes budget,
        so a flood cannot be hidden by its own rejections)."""
        now = time.monotonic()
        with self._lock:
            # Opportunistic cleanup so the dict cannot grow without bound.
            if len(self._keys) > 4096:
                self._keys = {
                    k: w for k, w in self._keys.items() if now < w.reset_at
                }
            window = self._keys.setdefault(key, _Window())
            per_key_ok = self._bump(window, self.per_key_limit, now)
            global_ok = self._bump(self._global, self.global_limit, now)
        return per_key_ok and global_ok

    def reset(self) -> None:
        """Test-only — clear all counters."""
        with self._lock:
            self._keys.clear()
            self._global = _Window()


# One shared instance for the redeem endpoint: ~10 attempts/min per source
# IP, ~100/min across all sources (plan B.12).
redeem_rate_limiter = FixedWindowRateLimiter(per_key_limit=10, global_limit=100)
