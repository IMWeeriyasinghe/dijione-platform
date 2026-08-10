from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import DocumentCategory
from app.db.base import Base, TimestampMixin


class Document(TimestampMixin, Base):
    """Lightweight document metadata (CLAUDE.md §38). Local MVP stores a
    demo-safe reference URL; production target is Azure Blob Storage /
    SharePoint behind the same field shape."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    talent_request_id: Mapped[int] = mapped_column(
        ForeignKey("talent_requests.id", ondelete="CASCADE"), index=True
    )
    file_name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(32), default=DocumentCategory.OTHER.value)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    storage_reference: Mapped[str] = mapped_column(String(500))
