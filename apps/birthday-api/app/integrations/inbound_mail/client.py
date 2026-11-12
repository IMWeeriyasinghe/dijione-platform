"""Inbound supplier-mail transport — polling only (Phase 1 §H.0). No
webhook, no Graph subscription, no renewal job. ``list_messages_since``
returns messages newer than the poll watermark, oldest first."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class InboundMessage:
    id: str  # provider (Graph) message id — the dedupe key
    from_address: str
    subject: str
    body_text: str
    received_at: datetime | None = None
    in_reply_to: list[str] = field(default_factory=list)  # message-ids this replies to
    references: list[str] = field(default_factory=list)
    attachment_count: int = 0


class InboundMailClient(ABC):
    @abstractmethod
    def list_messages_since(self, watermark: datetime | None, *, limit: int = 50) -> list[InboundMessage]:
        ...


class InboundMailNotConfiguredError(Exception):
    """Raised by GraphInboundMailClient when the mailbox / Graph app is not
    configured — DEV uses MockInboundMailClient instead."""
