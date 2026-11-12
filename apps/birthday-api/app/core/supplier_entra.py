"""Microsoft Entra ID id_token validation for the Birthday Supplier Portal.

Deliberately self-contained (not imported from platform-api — services do
not share process code). Same proven pattern as
``platform-api/app/core/security.py::EntraTokenVerifier``: RS256 signature
against Entra's JWKS, plus issuer / audience / tenant / expiry / nonce.

Used only inside ``/api/birthday/supplier/auth/token``. The DijiOne-format
supplier session token minted afterwards is what every supplier-portal
route actually trusts — Entra never authorizes DijiBirthday access on its
own; an ACTIVE ``SupplierUser`` match is still required.
"""

from __future__ import annotations

import time
from functools import lru_cache

import httpx
from jose import JWTError, jwt

from app.core.config import get_settings


class InvalidSupplierTokenError(Exception):
    """A supplier Entra id_token failed validation."""


class SupplierEntraVerifier:
    _JWKS_TTL_SECONDS = 3600

    def __init__(self) -> None:
        self._jwks: dict | None = None
        self._jwks_fetched_at: float = 0.0

    def _get_jwks(self) -> dict:
        now = time.monotonic()
        if self._jwks is None or now - self._jwks_fetched_at > self._JWKS_TTL_SECONDS:
            resp = httpx.get(get_settings().supplier_entra_jwks_uri, timeout=5.0)
            resp.raise_for_status()
            self._jwks = resp.json()
            self._jwks_fetched_at = now
        return self._jwks

    def verify_id_token(self, id_token: str, *, nonce: str | None = None) -> dict:
        settings = get_settings()
        try:
            header = jwt.get_unverified_header(id_token)
        except JWTError as exc:
            raise InvalidSupplierTokenError(f"malformed token: {exc}") from exc

        keys = self._get_jwks().get("keys", [])
        key = next((k for k in keys if k.get("kid") == header.get("kid")), None)
        if key is None:
            # signing-key roll — force one refresh
            self._jwks = None
            keys = self._get_jwks().get("keys", [])
            key = next((k for k in keys if k.get("kid") == header.get("kid")), None)
        if key is None:
            raise InvalidSupplierTokenError("no matching signing key in Entra JWKS")

        try:
            claims = jwt.decode(
                id_token,
                key,
                algorithms=["RS256"],
                audience=settings.supplier_entra_client_id,
                issuer=settings.supplier_entra_issuer,
                options={"require": ["exp", "iss", "aud"]},
            )
        except JWTError as exc:
            raise InvalidSupplierTokenError(str(exc)) from exc

        if settings.supplier_entra_tenant_id and claims.get("tid") != settings.supplier_entra_tenant_id:
            raise InvalidSupplierTokenError("token tenant (tid) does not match SUPPLIER_ENTRA_TENANT_ID")
        if nonce is not None and claims.get("nonce") != nonce:
            raise InvalidSupplierTokenError("nonce mismatch")
        return claims


@lru_cache
def get_supplier_entra_verifier() -> SupplierEntraVerifier:
    return SupplierEntraVerifier()
