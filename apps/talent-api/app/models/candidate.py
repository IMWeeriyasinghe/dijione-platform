from __future__ import annotations

from sqlalchemy import Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import CandidateAvailability
from app.db.base import Base, TimestampMixin


class Candidate(TimestampMixin, Base):
    """Master candidate profile. One row per human being — never duplicated
    across clients. See CLAUDE.md §19 (Candidate Ownership Rule).

    ``email`` is nullable and not unique — a real Lever contact can carry an
    explicit empty email, so dedup for Lever-sourced rows is on
    ``lever_external_id`` (partial-unique) instead. The manual "Add
    Candidate" flow keeps its own app-level get-by-email soft-dedup."""

    __tablename__ = "candidates"
    __table_args__ = (
        Index(
            "uq_candidates_lever_external_id",
            "lever_external_id",
            unique=True,
            sqlite_where=text("lever_external_id IS NOT NULL"),
            postgresql_where=text("lever_external_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
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
    lever_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    applications: Mapped[list[Application]] = relationship(  # noqa: F821
        back_populates="candidate", cascade="all, delete-orphan"
    )
