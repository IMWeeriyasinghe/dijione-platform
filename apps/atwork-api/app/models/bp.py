"""Business Partner role models for DijiAtWork."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class AtworkBPGrant(Base):
    """Records who currently holds the DijiAtWork BP role.

    A row with is_active=True means the employee has BP access.
    Revocation sets is_active=False and records revoked_by + revoked_at.
    """

    __tablename__ = "atwork_bp_grants"
    __table_args__ = (
        Index("ix_bp_grants_active", "platform_user_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform_user_id: Mapped[int] = mapped_column(Integer)
    granted_by: Mapped[int] = mapped_column(Integer)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AtworkBPEmployeeScope(Base):
    """Maps a BP to the employees they can see in Management.

    An active BP with no rows here sees an empty Management view (fail-closed).
    """

    __tablename__ = "atwork_bp_employee_scope"
    __table_args__ = (
        Index("ix_bp_scope_bp_active", "bp_platform_user_id", "is_active"),
        UniqueConstraint("bp_platform_user_id", "employee_platform_user_id", name="uq_bp_employee"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bp_platform_user_id: Mapped[int] = mapped_column(Integer)
    employee_platform_user_id: Mapped[int] = mapped_column(Integer)
    assigned_by: Mapped[int] = mapped_column(Integer)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    removed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
