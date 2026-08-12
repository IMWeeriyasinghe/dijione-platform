from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Permission(TimestampMixin, Base):
    """Atomic action a Role can bundle (DijiOne Phase 2 authorization model,
    CLAUDE.md-extension §19-20). ``module_key`` is null for platform-level
    permissions (e.g. Admin Center access)."""

    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("key", name="uq_permissions_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    module_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(64), default="General")


class Role(TimestampMixin, Base):
    """Named permission bundle. Platform-level when ``module_key`` is null
    (matched against ``User.platform_role``); module-scoped otherwise
    (matched against ``UserModuleRole.role`` for that ``module_key``).

    ``key`` is the stable string identifier already used throughout the
    codebase (e.g. "TA_MEMBER", "PLATFORM_ADMIN") — Role is a new layer on
    top of the existing string-keyed role columns, not a replacement for
    them, so no existing consumer of ``UserModuleRole.role`` or
    ``User.platform_role`` needs to change.
    """

    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("module_key", "key", name="uq_roles_module_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    module_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    key: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=True)

    role_permissions: Mapped[list[RolePermission]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )

    role: Mapped[Role] = relationship(back_populates="role_permissions")
    permission: Mapped[Permission] = relationship()
