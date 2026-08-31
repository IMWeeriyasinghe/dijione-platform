from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class RecruitmentCandidate(TimestampMixin, Base):
    """Lever Contact facts — a *source read model*, not an
    application-owned person record.

    DijiTalentFlow keeps its own ``Candidate`` master (one row per human,
    application-owned, may carry manual + recruiter workflow state). This
    table holds only what Lever reports about a contact, keyed by the
    stable Lever Contact id. A consumer projects/links these facts into its
    own master record over the recruitment-api HTTP contract — never by a
    cross-database join.
    """

    __tablename__ = "recruitment_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lever_contact_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)

    full_name: Mapped[str] = mapped_column(String(255), default="")
    email: Mapped[str] = mapped_column(String(255), default="", index=True)
    headline: Mapped[str] = mapped_column(String(255), default="")
    tags: Mapped[str] = mapped_column(Text, default="")  # JSON-encoded list[str]
    sources: Mapped[str] = mapped_column(Text, default="")  # JSON-encoded list[str]

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
