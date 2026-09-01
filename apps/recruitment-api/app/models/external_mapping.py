from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import SyncStatus
from app.db.base import Base, TimestampMixin


class ExternalMapping(TimestampMixin, Base):
    """Maps an internal domain record to its external provider record.

    Prevents duplicate creation on repeated webhook delivery — a mapping
    lookup (provider, external_object_type, external_id) must be idempotent.
    """

    __tablename__ = "external_mappings"
    __table_args__ = (
        UniqueConstraint(
            "provider", "external_object_type", "external_id", name="uq_external_object"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    external_object_type: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(128), index=True)
    internal_object_type: Mapped[str] = mapped_column(String(64))
    internal_id: Mapped[int] = mapped_column(Integer, index=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(16), default=SyncStatus.PENDING.value)
    sync_error: Mapped[str] = mapped_column(Text, default="")
