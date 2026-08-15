from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import PostingClientMappingStatus
from app.db.base import Base, TimestampMixin


class PostingClientMapping(TimestampMixin, Base):
    """The trusted, DijiOne-owned authorization relationship between a
    Lever Posting and a verified DijiOne Client.

    This is a deliberately separate table from ``Posting`` (not columns on
    it) so that Lever-sourced data and DijiOne-owned authorization/
    provenance data never share a row — a future re-sync of ``Posting``
    fields from Lever can never clobber verification state, and a future
    HubSpot-backed or multi-source reconciliation is additive rather than a
    schema change.

    Every ingested Posting gets a mapping row created at ingest time with
    status=UNMAPPED, client_id=None, so callers can always join rather than
    handle a missing-row case. A client-scoped caller must only ever see a
    Posting (or anything under it) when status == VERIFIED and
    client_id == their own client_id — this must be enforced at the
    repository/query level, never by tag/title-text inference.
    """

    __tablename__ = "posting_client_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    posting_id: Mapped[int] = mapped_column(
        ForeignKey("postings.id", ondelete="CASCADE"), unique=True, index=True
    )
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), default=PostingClientMappingStatus.UNMAPPED.value, index=True
    )
    source: Mapped[str] = mapped_column(String(32), default="")
    verified_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    posting: Mapped[Posting] = relationship(back_populates="client_mapping")  # noqa: F821
