from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(128))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[int] = mapped_column(Integer)
    previous_state: Mapped[str] = mapped_column(Text, default="")
    new_state: Mapped[str] = mapped_column(Text, default="")
    event_metadata: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # The DijiOne user an administrative event is about (their account, an
    # application assignment, a group membership), so one person's access
    # history can be listed whatever entity the event was recorded against.
    subject_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # Caller-chosen, so a retried delivery cannot record the event twice. NULL
    # for callers that do not send one; NULLs never collide.
    event_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
