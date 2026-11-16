from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ProtectedAdmin(TimestampMixin, Base):
    """An administrator whose SUPER_ADMIN privilege cannot be removed through DijiOne.

    The row is the policy. It is written only by a migration (or by the infrastructure-level
    recovery procedure in docs/platform/protected-super-admin.md); no application API creates,
    edits or deletes it, and the flush guard in ``app/services/protected_admin.py`` refuses any
    attempt to do so through the ORM. The identity is the normalised e-mail address, plus the
    Entra object id once the person has signed in, so the policy never depends on an
    environment-specific database id.
    """

    __tablename__ = "protected_admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    entra_object_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    required_role: Mapped[str] = mapped_column(String(32), default="SUPER_ADMIN")
