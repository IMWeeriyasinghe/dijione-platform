from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, false
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
    # Set only from a verified Entra sign-in. See entra_service.is_internal_employee.
    internal_employee: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Set when the identity was verified against the Entra directory (Microsoft Graph) rather than,
    # or before, a first sign-in. See app/services/directory_verification.py.
    directory_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # BambooHR Employee Number, verbatim (leading zeros kept), recorded from a matched employee record.
    employee_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Whether this person matches a BambooHR employee record: MATCHED / NOT_FOUND / UNKNOWN, or LEGACY
    # (eligible before employee-record checks existed; kept until reconciled). Default employee access
    # requires MATCHED or LEGACY. See AuthorizationService.is_eligible_employee.
    employee_record_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    employee_record_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Bumped, inside the same transaction, by every change that can alter what this
    # person may do (see ``app/services/access_version.py``). Session tokens carry the
    # value they were issued under (``av``); a token older than the current value is
    # revoked and must be refreshed. Never decremented, never time-based.
    access_version: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), default=0, server_default="0")

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
    # One assignment per user and application: a second row would survive a revocation.
    __table_args__ = (UniqueConstraint("user_id", "module_key", name="uq_user_module_roles_user_module"),)

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
