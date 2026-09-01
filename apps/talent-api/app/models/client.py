from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Client(TimestampMixin, Base):
    """DijiTalentFlow's extension of a platform-owned client organisation
    (Architecture Completion Plan §6.1). Canonical identity — the stable
    ``public_id``, the canonical name, the lifecycle status — is owned by
    ``platform-api``; this row references it via ``platform_client_id`` and
    holds only TalentFlow-specific attributes (industry, account manager)
    plus the local integer ``id`` that TalentFlow's own foreign keys use.
    """

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # The platform Client.public_id this row extends. Nullable through the
    # transition; the resolver in app/api/deps.py maps a client-scope claim
    # to this column.
    platform_client_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account_manager: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")

    talent_requests: Mapped[list[TalentRequest]] = relationship(  # noqa: F821
        back_populates="client"
    )
