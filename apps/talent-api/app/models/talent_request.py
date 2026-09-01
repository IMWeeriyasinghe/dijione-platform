from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text, text
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
    __table_args__ = (
        Index(
            "uq_talent_requests_posting_ref",
            "provider",
            "posting_external_id",
            unique=True,
            sqlite_where=text("posting_external_id IS NOT NULL"),
            postgresql_where=text("posting_external_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)

    # Source-relationship key (system-generated requests only — see
    # VerifiedPostingPromotionReconciler). NULL for pre-existing/non-Lever
    # rows. Mirrors PostingClientMapping's (provider, posting_external_id)
    # key rather than a local FK, since the posting read model lives in
    # recruitment-api's own database.
    provider: Mapped[str] = mapped_column(String(32), default="LEVER")
    posting_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

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

    # No FK to `users.id` — User is owned by platform-api's own database now.
    created_by: Mapped[int] = mapped_column(Integer)

    client: Mapped[Client] = relationship(back_populates="talent_requests")  # noqa: F821
    applications: Mapped[list[Application]] = relationship(  # noqa: F821
        back_populates="talent_request", cascade="all, delete-orphan"
    )
