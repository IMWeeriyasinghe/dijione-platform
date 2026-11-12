from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class SupplierUser(TimestampMixin, Base):
    """Application-level authorization mapping for the supplier portal:
    ``entra_object_id`` (the durable Microsoft Entra ID B2B guest identity
    key) -> this row -> ``supplier_id`` -> supplier-scoped access. ``role``
    (SUPPLIER_USER | SUPPLIER_ADMIN) and ``status`` (ACTIVE | INACTIVE)
    gate portal access; ``status`` is re-checked on every request, not
    just at token issuance. No password / magic-link fields by design —
    Entra B2B guest is the only production auth mechanism."""

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

    # Onboarding-state visibility for internal admins (Phase 1 §1.6). None
    # until each milestone: invited_at = IT recorded the B2B invite;
    # linked_at = entra_object_id first stamped; last_login_at = each
    # successful supplier session mint.
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    linked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    supplier: Mapped[Supplier] = relationship(back_populates="users")  # noqa: F821

    @property
    def onboarding_state(self) -> str:
        if self.status == "INACTIVE":
            return "INACTIVE"
        if self.last_login_at is not None:
            return "ACTIVE"
        if self.entra_object_id is not None or self.linked_at is not None:
            return "LINKED"
        if self.invited_at is not None:
            return "INVITED"
        return "NOT_INVITED"
