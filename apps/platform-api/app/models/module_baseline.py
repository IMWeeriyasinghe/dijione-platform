from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ModuleBaselineRole(Base):
    """A module role every eligible internal employee holds without an assignment.
    Derived at read time by ``AuthorizationService``; no per-user rows exist."""

    __tablename__ = "module_baseline_roles"

    module_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    role: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
