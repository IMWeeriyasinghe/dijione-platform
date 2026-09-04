"""Correlation-ID propagation for the DijiOne distributed backend.

A request entering any service is tagged with a correlation id — taken from
the inbound ``X-Correlation-Id`` header if present, otherwise generated. The
id is stored in a :class:`contextvars.ContextVar` for the life of the
request, echoed on the response, and attached to every outbound internal
HTTP call this service makes (see ``PlatformClient`` /
``RecruitmentSourceClient`` / ``EmployeeDirectoryClient``), so one logical
request can be followed across services in the logs.

Intentionally tiny: one pure-ASGI middleware, one context var, one logging
filter. No new framework, no dependency beyond the stdlib.
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar

CORRELATION_HEADER = "x-correlation-id"
_FALLBACK_HEADERS = ("x-request-id", "x-ms-request-id", "traceparent")

_correlation_id: ContextVar[str | None] = ContextVar("dijione_correlation_id", default=None)


def get_correlation_id() -> str | None:
    """The current request's correlation id, or ``None`` outside a request."""
    return _correlation_id.get()


def set_correlation_id(value: str | None) -> None:
    _correlation_id.set(value)


def new_correlation_id() -> str:
    return uuid.uuid4().hex[:16]


class CorrelationIdMiddleware:
    """Pure-ASGI middleware. ``app.add_middleware(CorrelationIdMiddleware)``."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        cid = headers.get(CORRELATION_HEADER)
        if not cid:
            for h in _FALLBACK_HEADERS:
                if headers.get(h):
                    cid = headers[h].split("-")[0][:32]  # traceparent -> trace-id-ish
                    break
        cid = cid or new_correlation_id()
        token = _correlation_id.set(cid)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                message["headers"] = [
                    (k, v) for (k, v) in message["headers"] if k.decode().lower() != CORRELATION_HEADER
                ]
                message["headers"].append((CORRELATION_HEADER.encode(), cid.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            _correlation_id.reset(token)


class CorrelationIdFilter(logging.Filter):
    """Adds ``correlation_id`` to every log record. A service that adopts a
    custom log format can then reference ``%(correlation_id)s``; if it
    doesn't, this filter is harmless."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id() or "-"
        return True
