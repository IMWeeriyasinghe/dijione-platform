from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Posting(TimestampMixin, Base):
    """Read-model mirror of a Lever Posting — the real job-demand entity in
    this tenant (Lever Requisitions are confirmed unused). Pure source data:
    every field here can be freely overwritten by a future re-sync from
    Lever.

    Client trust/visibility is NOT here — it is a DijiTalentFlow decision
    (``PostingClientMapping`` in talent-api). ``tags`` are exposed to
    consumers as a diagnostic + as the input to the governed DTC parse; a
    consumer must never use raw tags/title/team as an authorization signal.
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
    tags: Mapped[str] = mapped_column(Text, default="")  # JSON-encoded list[str]

    lever_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lever_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    archived: Mapped[bool] = mapped_column(Boolean, default=False)
