from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import DtcResolutionStatus, PostingClientMappingStatus
from app.db.base import Base, TimestampMixin


class PostingClientMapping(TimestampMixin, Base):
    """The trusted, DijiTalentFlow-owned authorization relationship between a
    Recruitment Source posting and a verified canonical Client.

    Keyed on ``(provider, posting_external_id)`` — the STABLE provider id —
    not a local foreign key, since the posting read model lives in
    recruitment-api's database now (Architecture Completion Plan §6 /
    CLAUDE.md data-ownership rule 6). A client-scoped caller may only ever
    see a posting when ``status == VERIFIED AND client_id == their own`` —
    enforced by an inner join at the repository layer, never by
    tag/title-text inference.

    Trust + DTC-reconciliation provenance columns are unchanged: a re-key of
    the posting reference must not disturb verification/audit state.
    """

    __tablename__ = "posting_client_mappings"
    __table_args__ = (
        UniqueConstraint("provider", "posting_external_id", name="uq_posting_client_mapping_ref"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), default="LEVER", index=True)
    posting_external_id: Mapped[str] = mapped_column(String(128), index=True)

    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), default=PostingClientMappingStatus.UNMAPPED.value, index=True
    )
    source: Mapped[str] = mapped_column(String(32), default="")
    verified_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # DTC-tag reconciliation provenance/diagnostics (audit only — never an
    # authorization signal on its own; the fail-closed query still keys on
    # status==VERIFIED AND client_id).
    dtc_source_tag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolution_status: Mapped[str] = mapped_column(
        String(32), default=DtcResolutionStatus.NO_DTC_TAG.value
    )
    last_reconciled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
