from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ApplicationModule(TimestampMixin, Base):
    """DijiOne module registry entry (CLAUDE.md §10)."""

    __tablename__ = "application_modules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    icon: Mapped[str] = mapped_column(String(64), default="LayoutGrid")
    route: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    # Whether this module's authorization reads client (customer) scope.
    # Admin Center shows Client Scope only when true.
    supports_client_scope: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    required_roles: Mapped[str] = mapped_column(
        String(255), default=""
    )  # comma-separated role keys; empty = any authenticated platform user
