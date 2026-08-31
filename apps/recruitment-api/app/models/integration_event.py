from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import ProcessingStatus
from app.db.base import Base, utcnow


class IntegrationEvent(Base):
    """Log of every inbound webhook/sync event, keyed for idempotency.

    A duplicate (provider, external_event_id) delivery is recorded but
    marked IGNORED_DUPLICATE rather than re-processed, per CLAUDE.md §65.
    """

    __tablename__ = "integration_events"
    __table_args__ = (
        UniqueConstraint("provider", "external_event_id", name="uq_provider_event"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    external_event_id: Mapped[str] = mapped_column(String(128))
    event_type: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_status: Mapped[str] = mapped_column(
        String(32), default=ProcessingStatus.RECEIVED.value
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    payload_reference: Mapped[str] = mapped_column(Text, default="")
