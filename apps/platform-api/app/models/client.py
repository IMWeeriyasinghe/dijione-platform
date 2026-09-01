"""Canonical Client / Organisation identity — platform-owned master
reference data (Architecture Completion Plan §6.1).

"Which organisations is Dijital Team a supplier to" is a DijiOne governance
decision, not a CRM fact, so the *identity* row lives here in
``platform-api`` next to the authorization scopes that reference it — the
same place the module registry and role catalogue live. Commercial / CRM
(HubSpot), when that domain is built, supplies *facts about* these clients
(industry, account owner, lifecycle) keyed by ``public_id`` and may propose
new organisations for an admin to confirm; it never owns this table.

Application services (talent-api today) hold their own extension row keyed
by ``public_id`` for domain-specific attributes — they never duplicate the
identity.

``public_id`` is the stable, non-sequential identifier every other service
stores (as ``client_ref`` on a scope row, ``platform_client_id`` on
talent-api's ``clients`` extension, ``client_public_id(s)`` in a JWT claim).
It survives a reseed; the integer ``id`` is internal to this database.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class ClientStatus:
    PROSPECT = "PROSPECT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"


class Client(TimestampMixin, Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Stable, non-sequential, immutable. Seeds use a readable slug
    # (``cli-abc-company``); runtime creation uses ``cli-<uuid4 hex[:12]>``.
    public_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(16), default=ClientStatus.ACTIVE)

    external_ids: Mapped[list[ClientExternalId]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )


class ClientExternalId(TimestampMixin, Base):
    """Crosswalk from a canonical client to its id in an external system or
    another DijiOne service. Populated by source domains later; used now to
    carry the ``talent-api`` legacy integer id through the transition so the
    Admin Center's existing client picker keeps working while scope rows are
    re-keyed onto ``client_ref``.
    """

    __tablename__ = "client_external_ids"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_client_external_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[str] = mapped_column(String(128))

    client: Mapped[Client] = relationship(back_populates="external_ids")
