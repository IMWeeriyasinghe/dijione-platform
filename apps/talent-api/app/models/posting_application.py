from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import ApplicationStatus, CanonicalStage
from app.db.base import Base, TimestampMixin


class PostingApplication(TimestampMixin, Base):
    """A Candidate's candidacy for a Lever Posting — the Lever-sourced
    counterpart of ``Application``, deliberately NOT the same table.

    ``Application`` links a Candidate to a DijiOne ``TalentRequest``, which
    always has a non-nullable ``client_id`` — that invariant exists because
    a TalentRequest is only ever created already-attached to a client via
    the client workflow. A raw Lever Opportunity has no client yet (that's
    exactly what ``PostingClientMapping`` resolves, separately and later).
    Writing Opportunities into ``Application`` would force inventing a
    client relationship, which is explicitly forbidden. This table exists
    so Candidate<->Posting candidacy data can be synced now, safely, with
    zero client assumption — a future, separately-approved step can decide
    whether/how a verified-client PostingApplication should also produce a
    real Application once its Posting's mapping is VERIFIED.
    """

    __tablename__ = "posting_applications"
    # No uniqueness on (candidate_id, posting_id): real Lever data confirms
    # a candidate can have multiple distinct Opportunities against the
    # same Posting (e.g. reapplication over time) — only the Lever
    # Opportunity id itself is a safe uniqueness boundary.

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
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

    candidate: Mapped[Candidate] = relationship()  # noqa: F821
    posting: Mapped[Posting] = relationship()  # noqa: F821
