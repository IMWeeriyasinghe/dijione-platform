from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class UserModuleClientScope(TimestampMixin, Base):
    """Client/portfolio scope for a module assignment (DijiOne Phase 2 §22).

    One ``UserModuleRole`` may own many scope rows — one per authorized
    client — or a single ``all_clients=True`` row meaning unrestricted
    cross-client access. TALENT_CLIENT assignments always carry exactly one
    non-``all_clients`` row matching ``UserModuleRole.client_id`` (kept in
    sync for backward compatibility with pre-Phase-2 single-tenant code
    paths). Staff assignments may carry a specific portfolio (several rows)
    or a single ``all_clients`` row.

    ``client_ref`` is the durable identifier: the ``public_id`` of a
    platform-owned ``Client`` (Architecture Completion Plan §6.1). The legacy
    bare ``client_id`` integer — historically *assumed* to equal talent-api's
    ``clients.id`` by seed-insertion order — is kept alongside it for one
    migration cycle and then dropped; new code reads ``client_ref``.
    """

    __tablename__ = "user_module_client_scopes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_module_role_id: Mapped[int] = mapped_column(
        ForeignKey("user_module_roles.id", ondelete="CASCADE"), index=True
    )
    client_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    client_ref: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    all_clients: Mapped[bool] = mapped_column(Boolean, default=False)

    user_module_role: Mapped[UserModuleRole] = relationship(  # noqa: F821
        back_populates="client_scopes"
    )
