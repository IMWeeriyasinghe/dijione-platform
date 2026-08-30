"""Microsoft Entra ID OIDC integration (Authorization Code + PKCE).

Entra performs *authentication*; DijiOne (``platform-api``) remains the
authority for *authorization* and issues its own signed session token from
the verified Entra identity, so every downstream service
(talent-api/birthday-api/spark-api, packages/auth-client-py) is unchanged.

Active only when ``AUTH_MODE=entra`` and the four ``ENTRA_*`` settings are
configured; otherwise every route here 501s and Dev Identity Mode
(``/api/auth/dev-*``) is the working path — see
docs/platform/authentication.md.

Flow:
  GET  /api/auth/entra/login-url  -> {authorize_url, flow_token}
       (Next.js /login sets flow_token as an httpOnly cookie, 302s to authorize_url)
  ...Entra redirects to <public>/api/auth/callback?code=&state=
  POST /api/auth/entra/token  {code, state, flow_token}
       -> verify -> resolve/provision User -> issue DijiOne session -> {access_token, user}
"""

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.routes.auth import _to_current_user_out
from app.core.config import get_settings
from app.core.security import InvalidTokenError, get_entra_verifier, issue_session_token
from app.db.session import get_db
from app.repositories.user_repo import UserRepository
from app.schemas.auth import TokenResponse
from app.services.claims_service import build_claims
from app.services.entra_service import EntraLoginRefusedError, resolve_entra_user

router = APIRouter(prefix="/api/auth/entra", tags=["auth-entra"])

_FLOW_TOKEN_TTL_MINUTES = 10
_FLOW_ISS = "dijione-entra-flow"


class EntraLoginUrlOut(BaseModel):
    authorize_url: str
    flow_token: str


class EntraTokenExchangeIn(BaseModel):
    code: str
    state: str
    flow_token: str


def _require_entra_configured() -> None:
    settings = get_settings()
    if settings.auth_mode != "entra":
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            "AUTH_MODE is not 'entra' for this environment — Dev Identity Mode is active. "
            "See docs/platform/authentication.md.",
        )
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
            f"Microsoft Entra ID SSO is selected but not fully configured. Missing: {', '.join(missing)}.",
        )


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    return verifier, challenge


def _sign_flow_token(state: str, nonce: str, verifier: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "iss": _FLOW_ISS,
        "iat": now,
        "exp": now + timedelta(minutes=_FLOW_TOKEN_TTL_MINUTES),
        "state": state,
        "nonce": nonce,
        "cv": verifier,
    }
    return jwt.encode(payload, settings.jwt_dev_secret, algorithm=settings.jwt_algorithm)


def _read_flow_token(flow_token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(
            flow_token,
            settings.jwt_dev_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=_FLOW_ISS,
        )
    except JWTError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid or expired login flow token: {exc}") from exc


@router.get("/login-url", response_model=EntraLoginUrlOut)
def get_login_url() -> EntraLoginUrlOut:
    _require_entra_configured()
    settings = get_settings()
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    verifier, challenge = _pkce_pair()
    params = {
        "client_id": settings.entra_client_id,
        "response_type": "code",
        "redirect_uri": settings.entra_redirect_uri,
        "response_mode": "query",
        "scope": "openid profile email",
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    authorize_url = f"{settings.entra_authority}/oauth2/v2.0/authorize?{urlencode(params)}"
    return EntraLoginUrlOut(authorize_url=authorize_url, flow_token=_sign_flow_token(state, nonce, verifier))


@router.post("/token", response_model=TokenResponse)
def exchange_code(payload: EntraTokenExchangeIn, db: Session = Depends(get_db)) -> TokenResponse:
    _require_entra_configured()
    settings = get_settings()

    flow = _read_flow_token(payload.flow_token)
    if not secrets.compare_digest(str(flow.get("state", "")), payload.state):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OAuth state mismatch")

    # --- authorization-code exchange (server-side; confidential client) ---
    try:
        token_resp = httpx.post(
            f"{settings.entra_authority}/oauth2/v2.0/token",
            data={
                "client_id": settings.entra_client_id,
                "client_secret": settings.entra_client_secret,
                "grant_type": "authorization_code",
                "code": payload.code,
                "redirect_uri": settings.entra_redirect_uri,
                "code_verifier": flow["cv"],
                "scope": "openid profile email",
            },
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Entra token endpoint unreachable: {exc}") from exc
    if token_resp.status_code != 200:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Entra rejected the authorization code")
    id_token = token_resp.json().get("id_token")
    if not id_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Entra response contained no id_token")

    # --- id_token validation ---
    try:
        claims = get_entra_verifier().verify_id_token(id_token, nonce=str(flow.get("nonce")))
    except (InvalidTokenError, httpx.HTTPError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid Entra id_token: {exc}") from exc

    # --- resolve / provision the DijiOne user (first-login policy C) ---
    try:
        user = resolve_entra_user(db, claims)
    except EntraLoginRefusedError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    # --- issue the DijiOne session token (unchanged downstream contract) ---
    session_token = issue_session_token(user.id, **build_claims(user, db))
    return TokenResponse(
        access_token=session_token, user=_to_current_user_out(user, UserRepository(db), db)
    )
