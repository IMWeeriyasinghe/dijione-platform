from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Posting(TimestampMixin, Base):
    """Read-model mirror of a Lever Posting (the real job-demand entity in
    this tenant — Lever Requisitions are confirmed unused, see live Lever
    tenant discovery). Pure source data: everything here can be freely
    overwritten by a future re-sync from Lever without touching
    authorization state, which lives in ``PostingClientMapping`` instead.

    Diagnostic fields (``tags``, ``team``, ``department``, description
    text) may be shown to internal/staff users as a hint but must never be
    used anywhere as an authorization signal for client visibility.
    """

    __tablename__ = "postings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lever_posting_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)

    title: Mapped[str] = mapped_column(String(255), default="")
    state: Mapped[str] = mapped_column(String(32), default="")
    team: Mapped[str] = mapped_column(String(255), default="")
    department: Mapped[str] = mapped_column(String(255), default="")
    location: Mapped[str] = mapped_column(String(255), default="")
    owner_user_id: Mapped[str] = mapped_column(String(128), default="")
    hiring_manager_user_id: Mapped[str] = mapped_column(String(128), default="")
    confidentiality: Mapped[str] = mapped_column(String(32), default="")
    tags: Mapped[str] = mapped_column(Text, default="")  # JSON-encoded list[str], diagnostic-only

    lever_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lever_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    archived: Mapped[bool] = mapped_column(Boolean, default=False)

    client_mapping: Mapped[PostingClientMapping | None] = relationship(  # noqa: F821
        back_populates="posting", uselist=False, cascade="all, delete-orphan"
    )
