from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import CandidateAvailability
from app.db.base import Base, TimestampMixin


class Candidate(TimestampMixin, Base):
    """Master candidate profile. One row per human being — never duplicated
    across clients. See CLAUDE.md §19 (Candidate Ownership Rule)."""

    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(64), default="")
    professional_title: Mapped[str] = mapped_column(String(255), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(255), default="")
    availability_status: Mapped[str] = mapped_column(
        String(32), default=CandidateAvailability.AVAILABLE.value
    )
    skills: Mapped[str] = mapped_column(String(500), default="")  # comma-separated
    cv_reference: Mapped[str] = mapped_column(String(255), default="")
    source: Mapped[str] = mapped_column(String(64), default="MANUAL")
    lever_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    applications: Mapped[list[Application]] = relationship(  # noqa: F821
        back_populates="candidate", cascade="all, delete-orphan"
    )
