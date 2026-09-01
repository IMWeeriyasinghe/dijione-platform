from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class AccessGroupStatus:
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class AccessGroup(TimestampMixin, Base):
    """Phase 2.6 reusable access group ("everyone on the TA Team").

    Additive, parallel to direct ``UserModuleRole`` assignment — never a
    replacement. ``group_type`` is a free-form classification string (e.g.
    TEAM/CLIENT/SYSTEM); ``SYSTEM`` groups are protected from deletion and
    deactivation by ``AdminService`` (see the guard in
    ``set_group_status``/``delete`` paths).
    """

    __tablename__ = "access_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default=AccessGroupStatus.ACTIVE)
    group_type: Mapped[str] = mapped_column(String(32), default="TEAM")

    memberships: Mapped[list[UserGroupMembership]] = relationship(
        back_populates="access_group", cascade="all, delete-orphan"
    )
    module_roles: Mapped[list[GroupModuleRole]] = relationship(
        back_populates="access_group", cascade="all, delete-orphan"
    )


class UserGroupMembership(TimestampMixin, Base):
    """A user's membership in an access group."""

    __tablename__ = "user_group_memberships"
    __table_args__ = (UniqueConstraint("user_id", "access_group_id", name="uq_user_group_membership"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    access_group_id: Mapped[int] = mapped_column(ForeignKey("access_groups.id", ondelete="CASCADE"))

    access_group: Mapped[AccessGroup] = relationship(back_populates="memberships")


class GroupModuleRole(TimestampMixin, Base):
    """Module-scoped role assignment granted to every active member of an
    access group. Mirrors ``UserModuleRole`` (app/models/user.py) shape."""

    __tablename__ = "group_module_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    access_group_id: Mapped[int] = mapped_column(ForeignKey("access_groups.id", ondelete="CASCADE"))
    module_key: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    access_group: Mapped[AccessGroup] = relationship(back_populates="module_roles")
    client_scopes: Mapped[list[GroupModuleClientScope]] = relationship(
        back_populates="group_module_role", cascade="all, delete-orphan"
    )


class GroupModuleClientScope(TimestampMixin, Base):
    """Client/portfolio scope for a group module assignment. Mirrors
    ``UserModuleClientScope`` (app/models/user_module_client_scope.py),
    including its ``client_ref`` -> platform-owned ``Client.public_id`` and
    the legacy ``client_id`` integer kept for one migration cycle."""

    __tablename__ = "group_module_client_scopes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_module_role_id: Mapped[int] = mapped_column(
        ForeignKey("group_module_roles.id", ondelete="CASCADE"), index=True
    )
    client_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    client_ref: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    all_clients: Mapped[bool] = mapped_column(Boolean, default=False)

    group_module_role: Mapped[GroupModuleRole] = relationship(back_populates="client_scopes")
