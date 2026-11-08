"""Holds audit and notification calls back until a transaction has committed.

Both are best-effort HTTP calls to Platform Core, so a database rollback cannot
undo them. Outside ``collect_side_effects`` they run immediately, as before.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

logger = logging.getLogger("talent-api.side_effects")

SideEffect = Callable[[], None]

_collector: ContextVar[list[SideEffect] | None] = ContextVar("side_effect_collector", default=None)


def dispatch_or_collect(effect: SideEffect) -> None:
    collected = _collector.get()
    if collected is None:
        effect()
    else:
        collected.append(effect)


@contextmanager
def collect_side_effects() -> Iterator[list[SideEffect]]:
    collected: list[SideEffect] = []
    token = _collector.set(collected)
    try:
        yield collected
    finally:
        _collector.reset(token)


def deliver_side_effects(effects: list[SideEffect], *, limit_seconds: float) -> None:
    """Send committed side effects, one failure never stopping the rest, and
    give up at ``limit_seconds`` so a Platform Core outage stays bounded."""
    started = time.monotonic()
    failed = 0
    for sent, effect in enumerate(effects):
        if time.monotonic() - started > limit_seconds:
            logger.warning("side effects undelivered=%s reason=time_limit", len(effects) - sent)
            return
        try:
            effect()
        except Exception:  # noqa: BLE001 - best-effort, as at every direct call site
            failed += 1
    if failed:
        logger.warning("side effects undelivered=%s reason=delivery_error", failed)
