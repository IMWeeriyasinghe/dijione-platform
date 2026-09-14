from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import ActorType
from app.db.base import Base, TimestampMixin


class OrderEvent(TimestampMixin, Base):
    """Audit/status-history spine — feeds the order-detail StageTimeline UI
    directly and is also mirrored into platform-api's AuditLog via
    audit_service.py (same dual-write pattern talent-api already uses)."""

    __tablename__ = "order_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("birthday_orders.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(32))
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # No FK to `users.id` — User is owned by platform-api's own database.
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_type: Mapped[str] = mapped_column(String(16), default=ActorType.SYSTEM.value)
    # Snapshotted at write time (Phase 1.6 §17) — an actor's *current* name
    # is never resolved later, so this stays historically accurate even if
    # the person's display name changes afterwards. NULL for any event
    # written before this column existed; the internal event-log UI falls
    # back to actor_type in that case.
    actor_display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    order: Mapped[BirthdayOrder] = relationship(back_populates="events")  # noqa: F821
