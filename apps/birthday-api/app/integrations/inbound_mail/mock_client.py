"""No-network mock — the default in DEV. Returns nothing on a normal poll;
the dev inject endpoint (``POST /api/birthday/internal/dev/inbound-email``)
feeds ``inbound_email_service.ingest_message`` directly so the full
correlation / quarantine pipeline is exercisable in hosted DEV without a
real mailbox or Graph credentials (mirrors ``EMAIL_SENDING_MODE=mock``)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.integrations.inbound_mail.client import InboundMailClient, InboundMessage


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


class MockInboundMailClient(InboundMailClient):
    # Class-level queue so tests can enqueue messages a poll should return.
    _queue: list[InboundMessage] = []

    @classmethod
    def enqueue(cls, message: InboundMessage) -> None:
        cls._queue.append(message)

    @classmethod
    def reset(cls) -> None:
        cls._queue = []

    def list_messages_since(self, watermark: datetime | None, *, limit: int = 50) -> list[InboundMessage]:
        wm = _aware(watermark)
        due = [
            m for m in type(self)._queue
            if wm is None or (m.received_at is not None and _aware(m.received_at) > wm)
        ]
        due.sort(key=lambda m: (m.received_at is None, _aware(m.received_at)))
        return due[:limit]
