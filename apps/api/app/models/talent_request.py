from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import (
    CanonicalStage,
    CustomerSuccessStatus,
    EngagementType,
    Priority,
    TalentRequestLifecycleStatus,
    TaStatus,
)
from app.db.base import Base, TimestampMixin


class TalentRequest(TimestampMixin, Base):
    __tablename__ = "talent_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)

    designation: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    required_skills: Mapped[str] = mapped_column(String(500), default="")  # comma-separated
    seniority: Mapped[str] = mapped_column(String(64), default="")
    location: Mapped[str] = mapped_column(String(255), default="")
    engagement_type: Mapped[str] = mapped_column(
        String(32), default=EngagementType.FULL_TIME.value
    )
    target_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")

    current_stage: Mapped[str] = mapped_column(
        String(32), default=CanonicalStage.REQUEST_SUBMITTED.value
    )
    lifecycle_status: Mapped[str] = mapped_column(
        String(32), default=TalentRequestLifecycleStatus.PENDING_REVIEW.value
    )
    customer_success_status: Mapped[str] = mapped_column(
        String(32), default=CustomerSuccessStatus.PENDING_REVIEW.value
    )
    ta_status: Mapped[str] = mapped_column(String(32), default=TaStatus.NOT_STARTED.value)
    client_safe_status_text: Mapped[str] = mapped_column(
        String(255), default="Request submitted — awaiting review"
    )
    priority: Mapped[str] = mapped_column(String(16), default=Priority.MEDIUM.value)

    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))

    client: Mapped[Client] = relationship(back_populates="talent_requests")  # noqa: F821
    applications: Mapped[list[Application]] = relationship(  # noqa: F821
        back_populates="talent_request", cascade="all, delete-orphan"
    )
