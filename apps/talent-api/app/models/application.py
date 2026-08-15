from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import ApplicationStatus, CanonicalStage
from app.db.base import Base, TimestampMixin


class Application(TimestampMixin, Base):
    """The relationship between one Candidate and one TalentRequest.

    This is the entity that makes cross-client candidate reuse possible
    (CLAUDE.md §23) — a candidate may have many Applications, one per
    TalentRequest they are considered for, without ever moving or
    duplicating the master Candidate record.
    """

    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("candidate_id", "talent_request_id", name="uq_candidate_request"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    talent_request_id: Mapped[int] = mapped_column(
        ForeignKey("talent_requests.id", ondelete="CASCADE"), index=True
    )

    current_stage: Mapped[str] = mapped_column(
        String(32), default=CanonicalStage.SOURCING.value
    )
    status: Mapped[str] = mapped_column(String(32), default=ApplicationStatus.ACTIVE.value)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    recruiter_notes: Mapped[str] = mapped_column(Text, default="")
    client_visible_notes: Mapped[str] = mapped_column(Text, default="")
    rejection_reason: Mapped[str] = mapped_column(String(500), default="")
    is_client_visible: Mapped[bool] = mapped_column(Boolean, default=False)

    lever_opportunity_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Raw Lever archive-reason text — internal/staff diagnostic only, never
    # returned in a client-safe DTO. `status` (ApplicationStatus) carries
    # the collapsed canonical outcome (HIRED / WITHDRAWN / REJECTED).
    lever_archive_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Minimal offer-lifecycle signal only — never compensation, documents,
    # or other sensitive offer fields (CLAUDE.md §60 discovery findings).
    lever_offer_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lever_offer_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    candidate: Mapped[Candidate] = relationship(back_populates="applications")  # noqa: F821
    talent_request: Mapped[TalentRequest] = relationship(  # noqa: F821
        back_populates="applications"
    )
    interviews: Mapped[list[Interview]] = relationship(  # noqa: F821
        back_populates="application", cascade="all, delete-orphan"
    )
