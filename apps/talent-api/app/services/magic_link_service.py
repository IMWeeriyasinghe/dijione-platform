"""DijiTalentFlow external client (magic-link) access — redemption of a
raw link token into a short-lived, client-scoped session JWT, and the
per-request trust re-check that backs every external route (plan B.2/B.5).

Security boundary (approved amendment): the session JWT is signed with
``settings.external_session_jwt_secret`` and issuer
``settings.external_session_jwt_issuer`` — a DIFFERENT secret + issuer from
the internal staff token. It is verified only by the dedicated
``_external_claims`` decoder in ``app/api/deps.py``; an internal decoder
rejects it on signature + issuer, and this decoder rejects an internal
token the same way. Possession of a valid session is never sufficient on
its own: ``get_talent_external_scope`` re-loads the ``MagicLinkGrant`` row
and re-checks ``revoked_at``/``expires_at`` on every request, and the
scoped ``client_id`` is always read from that row, never from the token or
any request parameter.

The raw token is never stored, logged, or put in an audit payload — only
its SHA-256 hex digest (``token_hash``).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from jose import jwt
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import (
    EXTERNAL_SESSION_PERMISSIONS,
    MODULE_TALENT_FLOW,
    MagicLinkScopeType,
    TalentFlowRole,
)
from app.models.client import Client
from app.models.magic_link_grant import MagicLinkGrant
from app.repositories.magic_link_grant_repo import MagicLinkGrantRepository
from app.services.audit_service import AuditService

# ~43 URL-safe chars, 256 bits of entropy — brute force is infeasible.
_RAW_TOKEN_BYTES = 32
_TOKEN_PREFIX_LEN = 8


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_raw_token() -> tuple[str, str, str]:
    """Returns ``(raw_token, token_hash, token_prefix)``. The raw token is
    the caller's responsibility to surface exactly once and never persist."""
    raw = secrets.token_urlsafe(_RAW_TOKEN_BYTES)
    return raw, hash_token(raw), raw[:_TOKEN_PREFIX_LEN]


class MagicLinkService:
    def __init__(self, db: Session, audit: AuditService | None = None):
        self.db = db
        self.repo = MagicLinkGrantRepository(db)
        self.audit = audit or AuditService()

    def redeem(self, raw_token: str, *, source_ip_hash: str | None = None) -> MagicLinkGrant | None:
        """Look the token up by hash and validate the grant. Returns the
        grant on success (caller commits), ``None`` for every failure mode
        — the route maps all of them to one indistinguishable 401, with no
        client name and no existence signal.
        """
        if not raw_token or not raw_token.strip():
            return None
        grant = self.repo.get_by_token_hash(hash_token(raw_token.strip()))
        if grant is None or not grant.is_valid:
            return None

        now = datetime.now(UTC)
        if grant.redeemed_at is None:
            grant.redeemed_at = now
        grant.last_used_at = now
        grant.use_count = (grant.use_count or 0) + 1

        # actor_id=None — no internal user behind this call. Never the raw
        # token; grant id + client public_id + a coarse IP hash only.
        self.audit.log(
            actor_id=None,
            action="talent.external.redeemed",
            entity_type="magic_link_grant",
            entity_id=grant.id,
            metadata={
                "grant_public_id": grant.public_id,
                "client_id": grant.client_id,
                "source_ip_hash": source_ip_hash,
                "use_count": grant.use_count,
            },
        )
        return grant

    # --- TA grant management (staff-authenticated, plan B.11) ------------

    def build_access_url(self, raw_token: str) -> str:
        """The one-time URL a TA copies. Token in the fragment only — never
        the path or query, so it is never sent in a Referer header or
        written to a server/access log."""
        base = get_settings().external_portal_base_url.rstrip("/")
        return f"{base}/access#{raw_token}"

    def create_grant(
        self,
        *,
        client_id: int,
        issued_by_user_id: int,
        contact_name: str = "",
        contact_email: str = "",
        expires_in_days: int | None = None,
    ) -> tuple[MagicLinkGrant, str]:
        """Mint a new grant for a client. Returns ``(grant, raw_token)`` —
        the raw token is surfaced to the TA exactly once and never stored.
        Caller commits."""
        settings = get_settings()
        days = expires_in_days or settings.external_grant_default_expiry_days
        raw, token_hash, token_prefix = generate_raw_token()
        now = datetime.now(UTC)
        grant = MagicLinkGrant(
            public_id=f"mlg-{uuid.uuid4().hex[:12]}",
            client_id=client_id,
            scope_type=MagicLinkScopeType.CLIENT_WORKSPACE.value,
            contact_name=contact_name.strip(),
            contact_email=contact_email.strip(),
            token_hash=token_hash,
            token_prefix=token_prefix,
            issued_by_user_id=issued_by_user_id,
            issued_at=now,
            expires_at=now + timedelta(days=days),
        )
        self.db.add(grant)
        self.db.flush()
        self.audit.log(
            actor_id=issued_by_user_id,
            action="talent.external.link_generated",
            entity_type="magic_link_grant",
            entity_id=grant.id,
            metadata={
                "grant_public_id": grant.public_id,
                "client_id": client_id,
                "contact_email": grant.contact_email,
                "expires_at": grant.expires_at.isoformat(),
            },
        )
        return grant, raw

    def revoke_grant(
        self, grant: MagicLinkGrant, *, revoked_by_user_id: int, audit_action: str = "link_revoked"
    ) -> MagicLinkGrant:
        """Immediate revocation — the next ``get_talent_external_scope``
        re-check fails. Idempotent: revoking an already-revoked grant emits
        nothing and changes nothing. Caller commits."""
        if grant.revoked_at is None:
            grant.revoked_at = datetime.now(UTC)
            grant.revoked_by_user_id = revoked_by_user_id
            self.audit.log(
                actor_id=revoked_by_user_id,
                action=f"talent.external.{audit_action}",
                entity_type="magic_link_grant",
                entity_id=grant.id,
                metadata={"grant_public_id": grant.public_id, "client_id": grant.client_id},
            )
        return grant

    def regenerate_grant(
        self, old_grant: MagicLinkGrant, *, actor_user_id: int
    ) -> tuple[MagicLinkGrant, str]:
        """Revoke the old grant (audited as ``link_regenerated``) and issue
        a fresh one for the same client + contact. Returns
        ``(new_grant, raw_token)``. Caller commits."""
        self.revoke_grant(
            old_grant, revoked_by_user_id=actor_user_id, audit_action="link_regenerated"
        )
        return self.create_grant(
            client_id=old_grant.client_id,
            issued_by_user_id=actor_user_id,
            contact_name=old_grant.contact_name,
            contact_email=old_grant.contact_email,
        )

    def mint_session_jwt(self, grant: MagicLinkGrant) -> tuple[str, int]:
        """Build the short-lived external session JWT for a (validated)
        grant. Returns ``(token, expires_in_seconds)``.

        Signed with the external secret/issuer. ``sub`` is the grant id as
        a plain integer string (``decode_claims`` requires ``int(sub)``).
        The client scope in the claim is advisory display only — every
        route still resolves the real ``client_id`` from the grant row.
        """
        settings = get_settings()
        client = self.db.get(Client, grant.client_id)
        client_public_id = client.platform_client_id if client else None

        now = datetime.now(UTC)
        ttl = timedelta(minutes=settings.external_session_jwt_ttl_minutes)
        claims = {
            "sub": str(grant.id),
            "iat": now,
            "exp": now + ttl,
            "iss": settings.external_session_jwt_issuer,
            "is_active": True,
            "full_name": grant.contact_name or "",
            "email": grant.contact_email or "",
            "platform_role": "PLATFORM_USER",
            "platform_permissions": [],
            "module_roles": {
                MODULE_TALENT_FLOW: {
                    "role": TalentFlowRole.TALENT_CLIENT.value,
                    "client_id": None,
                    "client_ids": None,
                    "client_public_id": client_public_id,
                    "client_public_ids": [client_public_id] if client_public_id else None,
                    "permissions": list(EXTERNAL_SESSION_PERMISSIONS),
                }
            },
            "external": {"grant_id": grant.id},
        }
        token = jwt.encode(claims, settings.external_session_jwt_secret, algorithm="HS256")
        return token, int(ttl.total_seconds())
