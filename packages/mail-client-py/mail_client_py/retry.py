"""Bounded exponential backoff for an outbox-style dispatcher.

Pure functions, no clock and no state: each consuming service keeps its own outbox (its own
database, its own dispatcher) and asks this module only "how long until the next attempt" and
"is this outcome worth retrying".
"""

from __future__ import annotations

from mail_client_py.transport import MailOutcome

DEFAULT_BASE_SECONDS = 60
DEFAULT_CAP_SECONDS = 60 * 60
DEFAULT_MAX_ATTEMPTS = 5


def backoff_seconds(attempt: int, *, base: int = DEFAULT_BASE_SECONDS, cap: int = DEFAULT_CAP_SECONDS) -> int:
    """Delay before attempt ``attempt + 1`` after ``attempt`` failed attempts (1-based):
    base, 2*base, 4*base, ... never above ``cap``."""
    if attempt < 1:
        return 0
    return min(cap, base * (2 ** (attempt - 1)))


def is_retryable(outcome: MailOutcome) -> bool:
    """Only a real transport failure is worth retrying. A policy refusal (BLOCKED / DISABLED)
    gives the same answer every time until someone changes configuration, and SUBMITTED /
    SIMULATED are final."""
    return outcome is MailOutcome.FAILED
