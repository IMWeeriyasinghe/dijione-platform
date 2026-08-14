from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class SupplierUser(TimestampMixin, Base):
    """Domain modeled now, portal built in Phase F. No auth fields yet —
    auth mechanism is a Phase F decision; this table only carries the
    ``supplier_id`` tenant-isolation boundary now."""

    __tablename__ = "supplier_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    # SUPPLIER_USER | SUPPLIER_ADMIN — portal-side role, distinct from the
    # internal BirthdayRole enum. Not yet consumed for finer-grained portal
    # permission gating (both roles get the same birthday.portal.* claims
    # today); carried now so the admin UI and future gating have it.
    role: Mapped[str] = mapped_column(String(32), default="SUPPLIER_USER")
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    # Microsoft Entra ID B2B guest join key (Phase-Next §5) — populated once
    # the guest identity is provisioned/linked; the ``oid`` claim from a
    # validated guest token resolves to this row -> supplier_id. Nullable
    # until provisioning completes. No password/magic-link fields — Entra
    # B2B guest is the only production auth mechanism for supplier users.
    entra_object_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)

    supplier: Mapped[Supplier] = relationship(back_populates="users")  # noqa: F821
