"""Microsoft Entra ID OIDC integration points (Phase 2 CR §7-8).

These routes are the concrete "code seams" the CR requires even though no
Entra app registration exists yet: the shape of the Authorization Code +
PKCE flow is fully wired, but every step that needs real tenant/client
credentials fails fast with a clear, typed error instead of silently
pretending to work. Once ``ENTRA_TENANT_ID`` / ``ENTRA_CLIENT_ID`` /
``ENTRA_CLIENT_SECRET`` / ``ENTRA_REDIRECT_URI`` are configured and
``EntraAuthProvider`` (app/core/security.py) is implemented against Entra's
JWKS, these two routes are what the Next.js login button and
``/api/auth/callback`` route handler call — no other application code
needs to change (CLAUDE.md §12 "single seam" contract).
"""

from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(prefix="/api/auth/entra", tags=["auth-entra"])


class EntraLoginUrlOut(BaseModel):
    authorize_url: str
    state: str


class EntraTokenExchangeIn(BaseModel):
    code: str
    code_verifier: str
    state: str


def _require_entra_configured() -> None:
    settings = get_settings()
    missing = [
        name
        for name, value in (
            ("ENTRA_TENANT_ID", settings.entra_tenant_id),
            ("ENTRA_CLIENT_ID", settings.entra_client_id),
            ("ENTRA_CLIENT_SECRET", settings.entra_client_secret),
            ("ENTRA_REDIRECT_URI", settings.entra_redirect_uri),
        )
        if not value
    ]
    if missing:
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            "Microsoft Entra ID SSO is not configured for this environment. "
            f"Missing: {', '.join(missing)}. Use Dev Identity Mode "
            "(DEV_IDENTITY_MODE=true) until an Entra app registration is "
            "available — see docs/platform/authentication.md.",
        )


@router.get("/login-url", response_model=EntraLoginUrlOut)
def get_login_url() -> EntraLoginUrlOut:
    """Build the Entra ID authorization URL for the OIDC Authorization Code
    + PKCE flow. The Next.js login page calls this, redirects the browser to
    ``authorize_url``, and stores ``state``/the PKCE verifier client-side to
    validate the callback (CLAUDE.md §7)."""
    _require_entra_configured()
    settings = get_settings()
    # Real implementation: generate a cryptographically random `state` and
    # PKCE `code_verifier`/`code_challenge` pair, persist `state` server-side
    # (or in a signed cookie) for callback validation, and build the
    # standard Microsoft identity platform v2.0 /authorize URL below.
    params = {
        "client_id": settings.entra_client_id,
        "response_type": "code",
        "redirect_uri": settings.entra_redirect_uri,
        "response_mode": "query",
        "scope": "openid profile email",
        "code_challenge_method": "S256",
    }
    authorize_url = (
        f"https://login.microsoftonline.com/{settings.entra_tenant_id}"
        f"/oauth2/v2.0/authorize?{urlencode(params)}"
    )
    return EntraLoginUrlOut(authorize_url=authorize_url, state="NOT_IMPLEMENTED")


@router.post("/token")
def exchange_code(payload: EntraTokenExchangeIn) -> dict:
    """Exchange an authorization code for tokens, validate them via
    ``EntraAuthProvider``, resolve/create the DijiOne ``User`` by
    ``entra_object_id`` (falling back to email on first login), and issue a
    DijiOne session the same way ``/api/auth/dev-login`` does. Not
    implemented until ``EntraAuthProvider.decode_token`` validates real
    Entra JWTs against Entra's JWKS (CLAUDE.md §7, §12)."""
    _require_entra_configured()
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        "Entra token exchange is not implemented yet — EntraAuthProvider "
        "raises NotImplementedError by design until JWKS validation is "
        "wired in (see app/core/security.py).",
    )
