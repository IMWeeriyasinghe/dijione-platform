from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class IntegrationEvent(Base):
    """Log of every inbound HubSpot webhook delivery, keyed for
    idempotency. No HubSpot event currently drives a mutation anywhere in
    DijiOne — this exists to prove the architecture and log activity for
    future use, and to make repeated deliveries provably harmless."""

    __tablename__ = "integration_events"
    __table_args__ = (
        UniqueConstraint("provider", "external_event_id", name="uq_provider_event"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), default="HUBSPOT", index=True)
    external_event_id: Mapped[str] = mapped_column(String(128))
    event_type: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_status: Mapped[str] = mapped_column(String(32), default="RECEIVED")
    payload_reference: Mapped[str] = mapped_column(Text, default="")
