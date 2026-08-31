from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import ApplicationStatus, CanonicalStage
from app.db.base import Base, TimestampMixin


class RecruitmentCandidacy(TimestampMixin, Base):
    """A Lever-sourced candidacy: one Lever Opportunity linking a
    ``RecruitmentCandidate`` (contact facts) to a ``Posting``.

    This is the source counterpart of DijiTalentFlow's client-owned
    ``Application``/``TalentRequest`` — deliberately a separate concept. A
    raw Lever Opportunity has no client (that is exactly what TalentFlow's
    ``PostingClientMapping`` resolves, separately). Uniqueness is on the
    Lever Opportunity id only — a contact can hold multiple Opportunities
    against the same Posting over time.
    """

    __tablename__ = "recruitment_candidacies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recruitment_candidate_id: Mapped[int] = mapped_column(
        ForeignKey("recruitment_candidates.id", ondelete="CASCADE"), index=True
    )
    posting_id: Mapped[int] = mapped_column(
        ForeignKey("postings.id", ondelete="CASCADE"), index=True
    )
    lever_opportunity_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)

    current_stage: Mapped[str] = mapped_column(
        String(32), default=CanonicalStage.SOURCING.value
    )
    status: Mapped[str] = mapped_column(String(32), default=ApplicationStatus.ACTIVE.value)
    lever_archive_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    candidate: Mapped[RecruitmentCandidate] = relationship()  # noqa: F821
    posting: Mapped[Posting] = relationship()  # noqa: F821
