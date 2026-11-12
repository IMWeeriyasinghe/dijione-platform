"""Birthday Supplier Portal — Microsoft Entra ID B2B guest sign-in.

Authorization Code + PKCE, confidential client, server-side code exchange —
the same proven pattern as platform-api's internal
``/api/auth/entra/*``. Entra proves *who the external person is*; a
matching ACTIVE ``SupplierUser`` is what grants DijiBirthday access
(``resolve_supplier_user``). Fail-closed for a valid Microsoft/guest
identity with no registered supplier.

Active only when ``SUPPLIER_AUTH_MODE=entra`` and the four
``SUPPLIER_ENTRA_*`` settings are configured; otherwise ``/login-url`` and
``/token`` return 501 and the dev persona picker
(``/api/birthday/internal/dev/*``) is the working path.
"""

from __future__ import annotations

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

from app.core.config import get_settings
from app.core.supplier_entra import InvalidSupplierTokenError, get_supplier_entra_verifier
from app.db.session import get_db
from app.services.supplier_auth import (
    SupplierAccessRefusedError,
    mint_supplier_session_token,
    record_supplier_login,
    resolve_supplier_user,
)

router = APIRouter(prefix="/api/birthday/supplier/auth", tags=["birthday-supplier-auth"])

_FLOW_TOKEN_TTL_MINUTES = 10
_FLOW_ISS = "dijibirthday-supplier-entra-flow"


class SupplierAuthConfigOut(BaseModel):
    supplier_auth_mode: str


class SupplierLoginUrlOut(BaseModel):
    authorize_url: str
    flow_token: str


class SupplierTokenExchangeIn(BaseModel):
    code: str
    state: str
    flow_token: str


class SupplierTokenOut(BaseModel):
    access_token: str


def _require_entra_configured() -> None:
    s = get_settings()
    if s.supplier_auth_mode != "entra":
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            "SUPPLIER_AUTH_MODE is not 'entra' — the dev persona picker is active.",
        )
    missing = [
        name
        for name, value in (
            ("SUPPLIER_ENTRA_TENANT_ID", s.supplier_entra_tenant_id),
            ("SUPPLIER_ENTRA_CLIENT_ID", s.supplier_entra_client_id),
            ("SUPPLIER_ENTRA_CLIENT_SECRET", s.supplier_entra_client_secret),
            ("SUPPLIER_ENTRA_REDIRECT_URI", s.supplier_entra_redirect_uri),
        )
        if not value
    ]
    if missing:
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            f"Supplier Entra sign-in selected but not fully configured. Missing: {', '.join(missing)}.",
        )


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    return verifier, challenge


def _sign_flow_token(state: str, nonce: str, verifier: str) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": _FLOW_ISS,
            "iat": now,
            "exp": now + timedelta(minutes=_FLOW_TOKEN_TTL_MINUTES),
            "state": state,
            "nonce": nonce,
            "cv": verifier,
        },
        s.platform_jwt_secret,
        algorithm=s.jwt_algorithm,
    )


def _read_flow_token(flow_token: str) -> dict:
    s = get_settings()
    try:
        return jwt.decode(
            flow_token, s.platform_jwt_secret, algorithms=[s.jwt_algorithm], issuer=_FLOW_ISS
        )
    except JWTError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Invalid or expired login flow token: {exc}"
        ) from exc


@router.get("/config", response_model=SupplierAuthConfigOut)
def supplier_auth_config() -> SupplierAuthConfigOut:
    """Public — the supplier-web app reads this to choose which sign-in UI
    to render (the persona picker vs a 'Sign in with Microsoft' button)."""
    return SupplierAuthConfigOut(supplier_auth_mode=get_settings().supplier_auth_mode)


@router.get("/login-url", response_model=SupplierLoginUrlOut)
def get_login_url() -> SupplierLoginUrlOut:
    _require_entra_configured()
    s = get_settings()
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    verifier, challenge = _pkce_pair()
    params = {
        "client_id": s.supplier_entra_client_id,
        "response_type": "code",
        "redirect_uri": s.supplier_entra_redirect_uri,
        "response_mode": "query",
        "scope": "openid profile email",
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    authorize_url = f"{s.supplier_entra_authority}/oauth2/v2.0/authorize?{urlencode(params)}"
    return SupplierLoginUrlOut(
        authorize_url=authorize_url, flow_token=_sign_flow_token(state, nonce, verifier)
    )


@router.post("/token", response_model=SupplierTokenOut)
def exchange_code(payload: SupplierTokenExchangeIn, db: Session = Depends(get_db)) -> SupplierTokenOut:
    _require_entra_configured()
    s = get_settings()

    flow = _read_flow_token(payload.flow_token)
    if not secrets.compare_digest(str(flow.get("state", "")), payload.state):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OAuth state mismatch")

    try:
        token_resp = httpx.post(
            f"{s.supplier_entra_authority}/oauth2/v2.0/token",
            data={
                "client_id": s.supplier_entra_client_id,
                "client_secret": s.supplier_entra_client_secret,
                "grant_type": "authorization_code",
                "code": payload.code,
                "redirect_uri": s.supplier_entra_redirect_uri,
                "code_verifier": flow["cv"],
                "scope": "openid profile email",
            },
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Entra token endpoint unreachable: {exc}"
        ) from exc
    if token_resp.status_code != 200:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Entra rejected the authorization code")
    id_token = token_resp.json().get("id_token")
    if not id_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Entra response contained no id_token")

    try:
        claims = get_supplier_entra_verifier().verify_id_token(
            id_token, nonce=str(flow.get("nonce"))
        )
    except (InvalidSupplierTokenError, httpx.HTTPError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid Entra id_token: {exc}") from exc

    try:
        supplier_user = resolve_supplier_user(db, claims)
    except SupplierAccessRefusedError as exc:
        # Generic 403 — a valid Microsoft/guest identity with no registered
        # ACTIVE SupplierUser must not learn why it was refused.
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    token = mint_supplier_session_token(supplier_user)
    record_supplier_login(db, supplier_user)
    return SupplierTokenOut(access_token=token)
