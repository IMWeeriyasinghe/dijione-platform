"""Delegated application access administration.

``ApplicationAdministrator``: a Super Admin's appointment of one person as an access administrator
of one application, with the explicit authority that goes with it (which employee roles they may
grant; for client-scoped applications, which clients). The appointment grants an
administrator-only role (see ``app.core.permissions.DELEGATION``); it never grants business
permissions.

``ApplicationAccessSuspension``: an application-scoped deny for one person. While it exists, the
person's direct, ordinary group and appointment grants for that application do not apply.
Mandatory access (default employee access and grants from SYSTEM groups) is never suspended.
"""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ApplicationAdministrator(TimestampMixin, Base):
    __tablename__ = "application_administrators"
    __table_args__ = (UniqueConstraint("user_id", "module_key", name="uq_application_administrators_user_module"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    module_key: Mapped[str] = mapped_column(String(64), index=True)
    # Role keys this administrator may grant (a subset of the application's delegable roles).
    grantable_roles: Mapped[list] = mapped_column(JSON, default=list)
    # Client public ids this administrator may grant; NULL means all clients. Used only by
    # applications that read client scope.
    client_authority: Mapped[list | None] = mapped_column(JSON, nullable=True)
    can_appoint_admins: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    appointed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ApplicationAccessSuspension(TimestampMixin, Base):
    __tablename__ = "application_access_suspensions"
    __table_args__ = (UniqueConstraint("user_id", "module_key", name="uq_application_access_suspensions_user_module"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    module_key: Mapped[str] = mapped_column(String(64), index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    suspended_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
