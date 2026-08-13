"""Authentication seam.

Production target: Microsoft Entra ID, OpenID Connect, Authorization Code
Flow + PKCE, bearer access tokens validated against Entra's JWKS (signature,
issuer, audience, expiry, role claims).

Local/demo target: DEV IDENTITY MODE. ``DevAuthProvider`` issues and
validates short-lived HS256 tokens for a fixed set of personas. Both
providers implement :class:`AuthProvider` so route/service code never
branches on which mode is active — only ``get_auth_provider`` does.

Phase 2.5: the token payload also carries signed authorization claims
(``platform_permissions``, ``module_roles``) computed at issuance by
``ClaimsService`` — this is what lets talent-api/birthday-api/spark-api
authorize requests without a synchronous call back to Platform Core on
every request. See ``docs/platform/service-contracts.md``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from jose import JWTError, jwt

from app.core.config import get_settings


class InvalidTokenError(Exception):
    pass


class AuthProvider(ABC):
    @abstractmethod
    def issue_token(self, user_id: int, **claims: object) -> str: ...

    @abstractmethod
    def decode_token(self, token: str) -> dict:
        """Return the token payload. Raises InvalidTokenError if invalid."""


class DevAuthProvider(AuthProvider):
    """Issues/validates dev-mode tokens for the local persona switcher.

    Not used in production. The production seam is EntraAuthProvider below,
    which validates real Entra-issued tokens instead of self-issuing them.
    """

    def issue_token(self, user_id: int, **claims: object) -> str:
        settings = get_settings()
        now = datetime.now(UTC)
        payload = {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(minutes=settings.jwt_expires_minutes),
            "iss": "dijione-dev-identity",
            **claims,
        }
        return jwt.encode(payload, settings.jwt_dev_secret, algorithm=settings.jwt_algorithm)

    def decode_token(self, token: str) -> dict:
        settings = get_settings()
        try:
            return jwt.decode(
                token,
                settings.jwt_dev_secret,
                algorithms=[settings.jwt_algorithm],
                issuer="dijione-dev-identity",
            )
        except JWTError as exc:
            raise InvalidTokenError(str(exc)) from exc


class EntraAuthProvider(AuthProvider):
    """Production seam — validates Microsoft Entra ID issued tokens.

    Not implemented in this MVP phase: no tenant/client credentials are
    available. Wiring this in later must not require changes to route or
    service code, only to ``get_auth_provider``.
    """

    def issue_token(self, user_id: int, **claims: object) -> str:
        raise NotImplementedError(
            "EntraAuthProvider does not issue tokens; Entra ID issues them. "
            "Configure ENTRA_TENANT_ID / ENTRA_CLIENT_ID and implement JWKS "
            "validation before disabling DEV_IDENTITY_MODE."
        )

    def decode_token(self, token: str) -> dict:
        raise NotImplementedError(
            "Entra ID token validation is not configured. Set "
            "DEV_IDENTITY_MODE=true during local development."
        )


@lru_cache
def get_auth_provider() -> AuthProvider:
    settings = get_settings()
    if settings.dev_identity_mode:
        return DevAuthProvider()
    return EntraAuthProvider()
