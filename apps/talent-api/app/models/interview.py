from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import InterviewStatus, InterviewType
from app.db.base import Base, TimestampMixin


class Interview(TimestampMixin, Base):
    __tablename__ = "interviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    interview_type: Mapped[str] = mapped_column(
        String(32), default=InterviewType.CLIENT_INTERVIEW.value
    )
    status: Mapped[str] = mapped_column(String(32), default=InterviewStatus.SCHEDULED.value)
    meeting_link: Mapped[str] = mapped_column(String(500), default="")
    client_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")

    application: Mapped[Application] = relationship(back_populates="interviews")  # noqa: F821
