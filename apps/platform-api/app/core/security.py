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

import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import httpx
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
    """Production seam kept for symmetry with ``AuthProvider``.

    DijiOne never validates a raw Entra token on a normal request path: the
    Entra id_token is verified exactly once, inside ``/api/auth/entra/token``
    (see :class:`EntraTokenVerifier`), and a DijiOne HS256 *session* token is
    issued from it. Every authenticated request — in ``dev`` or ``entra``
    mode — then carries that session token, which
    :func:`decode_session_token` validates. So this class must never be the
    thing that decodes a request's bearer token; if it somehow is, it raises
    :class:`InvalidTokenError` (a 401), never an unhandled 500.
    """

    def issue_token(self, user_id: int, **claims: object) -> str:
        raise NotImplementedError(
            "EntraAuthProvider does not issue tokens; Entra ID issues them, and "
            "DijiOne then mints its own session token via issue_session_token()."
        )

    def decode_token(self, token: str) -> dict:
        raise InvalidTokenError(
            "EntraAuthProvider cannot validate a DijiOne session token; "
            "decode_session_token() is the request-path validator."
        )


@lru_cache
def get_auth_provider() -> AuthProvider:
    settings = get_settings()
    if settings.dev_auth_enabled:
        return DevAuthProvider()
    return EntraAuthProvider()


# The DijiOne session token is always HS256 with issuer ``dijione-dev-identity``
# regardless of AUTH_MODE (see issue_session_token). ``DevAuthProvider`` holds
# exactly that HS256/issuer logic, so both the issuer and validator delegate to
# it — the names are historical.
_session_provider = DevAuthProvider()


def issue_session_token(user_id: int, **claims: object) -> str:
    """Mint the *DijiOne* session token every service consumes (HS256, signed
    authorization claims, issuer ``dijione-dev-identity``). This is issued by
    DijiOne regardless of auth mode — in Entra mode the upstream Entra
    id_token is verified, then this DijiOne token is issued from it, so
    talent-api/birthday-api/spark-api and packages/auth-client-py need no
    change. (The name kept for the issuer string is historical.)"""
    return _session_provider.issue_token(user_id, **claims)


def decode_session_token(token: str) -> dict:
    """Validate a DijiOne session token and return its payload. Raises
    :class:`InvalidTokenError` for a missing/garbage/expired/wrong-issuer
    token. This is the request-path validator used by ``get_current_user``
    in **every** auth mode — the session token format never changes when
    AUTH_MODE flips to ``entra`` (only how the user first proved identity
    does)."""
    return _session_provider.decode_token(token)


class EntraTokenVerifier:
    """Validates a Microsoft Entra ID **id_token** for the DijiOne DEV app
    registration: RS256 signature against Entra's JWKS, plus issuer,
    audience, tenant and expiry. Used only inside ``/api/auth/entra/token`` —
    the DijiOne session token issued afterwards is what everything else
    trusts."""

    _JWKS_TTL_SECONDS = 3600

    def __init__(self) -> None:
        self._jwks: dict | None = None
        self._jwks_fetched_at: float = 0.0

    def _get_jwks(self) -> dict:
        now = time.monotonic()
        if self._jwks is None or now - self._jwks_fetched_at > self._JWKS_TTL_SECONDS:
            settings = get_settings()
            resp = httpx.get(settings.entra_jwks_uri, timeout=5.0)
            resp.raise_for_status()
            self._jwks = resp.json()
            self._jwks_fetched_at = now
        return self._jwks

    def verify_id_token(self, id_token: str, *, nonce: str | None = None) -> dict:
        settings = get_settings()
        try:
            header = jwt.get_unverified_header(id_token)
        except JWTError as exc:
            raise InvalidTokenError(f"malformed token: {exc}") from exc

        keys = self._get_jwks().get("keys", [])
        key = next((k for k in keys if k.get("kid") == header.get("kid")), None)
        if key is None:
            # key roll — force one refresh
            self._jwks = None
            keys = self._get_jwks().get("keys", [])
            key = next((k for k in keys if k.get("kid") == header.get("kid")), None)
        if key is None:
            raise InvalidTokenError("no matching signing key in Entra JWKS")

        try:
            claims = jwt.decode(
                id_token,
                key,
                algorithms=["RS256"],
                audience=settings.entra_client_id,
                issuer=settings.entra_issuer,
                options={"require": ["exp", "iss", "aud"]},
            )
        except JWTError as exc:
            raise InvalidTokenError(str(exc)) from exc

        if settings.entra_tenant_id and claims.get("tid") != settings.entra_tenant_id:
            raise InvalidTokenError("token tenant (tid) does not match ENTRA_TENANT_ID")
        if nonce is not None and claims.get("nonce") != nonce:
            raise InvalidTokenError("nonce mismatch")
        return claims


@lru_cache
def get_entra_verifier() -> EntraTokenVerifier:
    return EntraTokenVerifier()
