"""Ready-made FastAPI dependency for services that authorize purely from
JWT claims (talent-api, birthday-api, spark-api) — no database join, no
call back to Platform Core. Optional: services are free to write their own
``Depends`` chain against ``decode_claims`` directly if they need something
this shape doesn't cover.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth_client_py.claims import AuthClaims, InvalidTokenError, decode_claims

_bearer_scheme = HTTPBearer(auto_error=False)


def make_get_claims(*, secret: str, algorithm: str = "HS256", issuer: str = "dijione-dev-identity") -> Callable[..., AuthClaims]:
    """Build a FastAPI dependency that resolves ``AuthClaims`` from the
    request's bearer token. Call once per service at module load time:

        get_claims = make_get_claims(secret=settings.jwt_dev_secret)

        @router.get("/requests")
        def list_requests(claims: AuthClaims = Depends(get_claims)): ...
    """

    def _get_claims(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    ) -> AuthClaims:
        if credentials is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
        try:
            claims = decode_claims(credentials.credentials, secret=secret, algorithm=algorithm, issuer=issuer)
        except InvalidTokenError as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc
        if not claims.is_active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
        return claims

    return _get_claims
