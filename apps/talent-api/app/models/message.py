from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Message(TimestampMixin, Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    talent_request_id: Mapped[int] = mapped_column(
        ForeignKey("talent_requests.id", ondelete="CASCADE"), index=True
    )
    # No FK to `users.id` — User is owned by platform-api's own database now
    # (see docs/platform/service-architecture.md "Data ownership"). The
    # sender's display name is captured at send time (below) rather than
    # resolved by a cross-service lookup on every read.
    sender_id: Mapped[int] = mapped_column(Integer)
    sender_name: Mapped[str] = mapped_column(String(255), default="")
    sender_role: Mapped[str] = mapped_column(String(64))
    body: Mapped[str] = mapped_column(Text)
