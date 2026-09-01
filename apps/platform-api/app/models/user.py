from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import PlatformRole
from app.db.base import Base, TimestampMixin
from app.models.user_module_client_scope import UserModuleClientScope


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    platform_role: Mapped[str] = mapped_column(
        String(32), default=PlatformRole.PLATFORM_USER.value
    )
    persona_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    avatar_color: Mapped[str | None] = mapped_column(String(16), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # DijiOne Phase 2 identity fields. A DijiOne user exists independently of
    # the auth provider; ``entra_object_id`` is the stable Microsoft identity
    # key once Entra SSO is wired in, and must never be required for Dev
    # Identity Mode to keep working.
    entra_object_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    identity_provider: Mapped[str] = mapped_column(String(32), default="DEV_IDENTITY")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    module_roles: Mapped[list[UserModuleRole]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserModuleRole(TimestampMixin, Base):
    """Module-scoped role assignment ("UserModuleAssignment").

    ``client_id`` is set only for DijiTalentFlow client-side roles
    (TALENT_CLIENT), scoping that user to a single tenant. Staff roles
    (TA_MEMBER / CUSTOMER_SUCCESS / TA_MANAGER) leave it null. Cross-client
    *portfolio* scope for staff is resolved from ``client_scopes`` via
    ``AuthorizationService``, not from this column.

    Architecture Completion Plan §6.1: canonical Client / Organisation
    identity is now platform-owned master data (``app/models/client.py``).
    ``client_ref`` is the durable reference — a ``Client.public_id``. The
    legacy bare ``client_id`` integer (historically *assumed* to equal
    talent-api's ``clients.id`` by seed order) is kept alongside for one
    migration cycle, then dropped.
    """

    __tablename__ = "user_module_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    module_key: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(64))
    client_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    client_ref: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship(back_populates="module_roles")
    client_scopes: Mapped[list[UserModuleClientScope]] = relationship(
        back_populates="user_module_role", cascade="all, delete-orphan"
    )
