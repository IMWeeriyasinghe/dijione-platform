from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class InboundEmail(TimestampMixin, Base):
    """Quarantine-only store for supplier emails that could NOT be safely
    correlated (Phase 1 §H.1 step 5) — never used for matched mail (that
    goes straight to ``SupplierCommunication``). Surfaced in the internal
    "Unmatched supplier email" queue; an authorized user links it to an
    order (promoting it to a real INBOUND ``SupplierCommunication``) or
    dismisses it. It never touches an order on its own."""

    __tablename__ = "inbound_emails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_message_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    from_address: Mapped[str] = mapped_column(String(320), default="")
    subject: Mapped[str] = mapped_column(String(500), default="")
    body_preview: Mapped[str] = mapped_column(Text, default="")
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attachment_count: Mapped[int] = mapped_column(Integer, default=0)
    # UNMATCHED | LINKED | DISMISSED
    status: Mapped[str] = mapped_column(String(16), default="UNMATCHED", index=True)
    reason: Mapped[str] = mapped_column(String(255), default="")
    linked_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    linked_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InboundPollState(TimestampMixin, Base):
    """Single-row watermark for the inbound mailbox poll (§H.0). The
    watermark only advances after a fully successful poll, so a failed run
    reprocesses from the same point — dedupe on ``provider_message_id``
    makes that safe."""

    __tablename__ = "inbound_poll_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
