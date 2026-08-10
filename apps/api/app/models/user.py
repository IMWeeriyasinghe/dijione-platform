from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import PlatformRole
from app.db.base import Base, TimestampMixin


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

    module_roles: Mapped[list[UserModuleRole]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserModuleRole(TimestampMixin, Base):
    """Module-scoped role assignment.

    ``client_id`` is set only for DijiTalentFlow client-side roles
    (TALENT_CLIENT), scoping that user to a single tenant. Staff roles
    (TA_MEMBER / CUSTOMER_SUCCESS / TA_MANAGER) leave it null, meaning
    cross-client visibility within their authorization scope.
    """

    __tablename__ = "user_module_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    module_key: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(64))
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=True, index=True
    )

    user: Mapped[User] = relationship(back_populates="module_roles")
