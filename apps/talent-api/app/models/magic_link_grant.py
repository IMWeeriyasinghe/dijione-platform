from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import MagicLinkGrantStatus, MagicLinkScopeType
from app.db.base import Base, TimestampMixin, utcnow


def _default_expiry() -> datetime:
    return utcnow() + timedelta(days=14)


class MagicLinkGrant(TimestampMixin, Base):
    """A DijiTalentFlow external client/prospect access grant (Phase B —
    magic-link architecture). Authentication/bootstrap only — never itself
    authorization. Every fact an external session needs (which client, is
    it still valid) is resolved server-side from THIS row on every request
    by ``get_talent_external_scope`` (``app/api/deps.py``); nothing about
    scope is ever trusted from the session JWT or a request parameter (see
    ``ExternalClaims`` in ``packages/auth-client-py``).

    ``token_hash`` is the SHA-256 hex digest of the raw, one-time-displayed
    token (``secrets.token_urlsafe(32)``) — the raw token itself is never
    stored, logged, or audited. ``token_prefix`` is a short, non-secret
    slice of the raw token kept only so a TA can visually disambiguate
    grants in the management screen; it grants no access on its own.

    ``public_id`` is an opaque admin-facing reference (e.g. ``mlg-<hex>``),
    not the secret — safe to show/log, mirroring ``Client.public_id``.

    Reusable by design (decision 3): a grant is not single-use. Validity is
    ``revoked_at IS NULL AND expires_at > now``, re-checked on every
    external request — never cached in the session JWT.
    """

    __tablename__ = "magic_link_grants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)

    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    scope_type: Mapped[str] = mapped_column(
        String(32), default=MagicLinkScopeType.CLIENT_WORKSPACE.value
    )

    # Lightweight v1 contact model (decision 5) — no separate
    # ExternalClientContact entity yet.
    contact_email: Mapped[str] = mapped_column(String(255), default="")
    contact_name: Mapped[str] = mapped_column(String(255), default="")

    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    token_prefix: Mapped[str] = mapped_column(String(16), default="")

    # No FK to `users.id` — User is owned by platform-api's own database.
    issued_by_user_id: Mapped[int] = mapped_column(Integer)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_default_expiry, index=True
    )

    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    use_count: Mapped[int] = mapped_column(Integer, default=0)

    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    @property
    def status(self) -> str:
        """Derived, never stored — computed fresh so a revoke/expiry takes
        effect immediately without a write."""
        if self.revoked_at is not None:
            return MagicLinkGrantStatus.REVOKED.value
        expires_at = self.expires_at
        # SQLite drops tzinfo on round-trip even for DateTime(timezone=True)
        # columns (PostgreSQL preserves it) — every value this model writes
        # is UTC (see `utcnow`/`_default_expiry`), so a naive read-back is
        # always a UTC instant, not a comparison ambiguity.
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            return MagicLinkGrantStatus.EXPIRED.value
        return MagicLinkGrantStatus.ACTIVE.value

    @property
    def is_valid(self) -> bool:
        return self.status == MagicLinkGrantStatus.ACTIVE.value
