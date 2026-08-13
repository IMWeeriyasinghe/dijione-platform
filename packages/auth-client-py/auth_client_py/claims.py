"""Verifies the signed authorization claims Platform Core embeds in every
access token (see ``apps/platform-api/app/services/claims_service.py``) and
exposes them as typed, immutable objects.

talent-api / birthday-api / spark-api use this instead of a database
join or a synchronous call back to Platform Core on every request — the
whole point of Phase 2.5's claims-based auth (CR §19-20). The trade-off is
staleness: a permission change in the Admin Center takes effect the next
time the affected user's token refreshes, not instantly. That trade-off is
made once here, not re-decided per service.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jose import JWTError, jwt


class InvalidTokenError(Exception):
    pass


@dataclass(frozen=True)
class ModuleRoleClaims:
    role: str
    client_id: int | None
    client_ids: list[int] | None  # None == unrestricted (ALL_CLIENTS)
    permissions: frozenset[str] = field(default_factory=frozenset)

    def has(self, permission_key: str) -> bool:
        return permission_key in self.permissions


@dataclass(frozen=True)
class AuthClaims:
    user_id: int
    is_active: bool
    full_name: str
    email: str
    platform_role: str
    platform_permissions: frozenset[str]
    module_roles: dict[str, ModuleRoleClaims]

    def module(self, module_key: str) -> ModuleRoleClaims | None:
        return self.module_roles.get(module_key)

    def has_platform_permission(self, permission_key: str) -> bool:
        return permission_key in self.platform_permissions


def decode_claims(
    token: str, *, secret: str, algorithm: str = "HS256", issuer: str = "dijione-dev-identity"
) -> AuthClaims:
    """Verify the token's signature and shape it into ``AuthClaims``.

    Raises ``InvalidTokenError`` for a bad signature, expired token, wrong
    issuer, or a payload missing the claims Platform Core is expected to
    have embedded (a token from before Phase 2.5, or from a
    misconfigured/EntraAuthProvider issuer, should fail loudly here rather
    than silently granting no access).
    """
    try:
        payload = jwt.decode(token, secret, algorithms=[algorithm], issuer=issuer)
    except JWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    try:
        user_id = int(payload["sub"])
        module_roles = {
            module_key: ModuleRoleClaims(
                role=claim["role"],
                client_id=claim.get("client_id"),
                client_ids=claim.get("client_ids"),
                permissions=frozenset(claim.get("permissions", [])),
            )
            for module_key, claim in payload.get("module_roles", {}).items()
        }
        return AuthClaims(
            user_id=user_id,
            is_active=bool(payload.get("is_active", True)),
            full_name=payload.get("full_name", ""),
            email=payload.get("email", ""),
            platform_role=payload.get("platform_role", "PLATFORM_USER"),
            platform_permissions=frozenset(payload.get("platform_permissions", [])),
            module_roles=module_roles,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidTokenError(f"Token is missing expected Phase 2.5 claims: {exc}") from exc
