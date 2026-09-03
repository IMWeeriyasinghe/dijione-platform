from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class RecruitmentPostingRef(TimestampMixin, Base):
    """A thin local projection of a Recruitment Source posting.

    It is **not** another canonical Lever store — recruitment-api owns that.
    talent-api keeps only what it needs to (a) run the fail-closed
    client-visibility join entirely locally and (b) keep the staff postings
    review screen + client-visible listing working when recruitment-api is
    briefly unavailable. Refreshed from recruitment-api's canonical posting
    DTO on every reconcile; a field here is a cached copy, never a source of
    truth.

    The parsed governed DTC tag is carried as a *fact* (recruitment-api
    parses it); the trust decision it feeds is ``PostingClientMapping``.
    """

    __tablename__ = "recruitment_posting_refs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), default="LEVER")
    external_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)

    title: Mapped[str] = mapped_column(String(255), default="")
    state: Mapped[str] = mapped_column(String(32), default="")
    location: Mapped[str] = mapped_column(String(255), default="")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)

    # Parsed governed DTC tag fact from recruitment-api (NO_TAG/OK/MALFORMED/MULTIPLE).
    dtc_status: Mapped[str] = mapped_column(String(16), default="NO_TAG")
    dtc_client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dtc_raw_tag: Mapped[str | None] = mapped_column(String(255), nullable=True)

    source_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # When Lever created the posting (fact, refreshed every sync) — shown
    # to staff as the postings-review "Created" column.
    lever_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
