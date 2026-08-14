"""Dev-only supplier persona provider (Phase-Next §5/§6) — the local/dry-run
stand-in for Microsoft Entra ID B2B guest auth in the supplier portal.

Hard-disabled outside development, mirroring the existing internal
DEV IDENTITY MODE persona switcher (CLAUDE.md §13): callers pick a seeded
``SupplierUser`` row and receive a token whose ``supplier`` claim is
resolved server-side from that row's own ``supplier_id`` — a caller can
select *which persona* to become, never *which supplier_id* to claim.
This keeps the authorization/isolation layer (``SupplierScope``,
repository-level ``supplier_id`` scoping) completely decoupled from the
identity source: swapping this for real Entra B2B later is a
token-issuance change only, no change to any downstream authorization
code.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from jose import jwt
from pydantic import BaseModel
from sqlalchemy import select

from app.core.config import get_settings
from app.core.constants import MODULE_BIRTHDAY, BirthdayRole
from app.db.session import SessionLocal
from app.models.supplier_user import SupplierUser

router = APIRouter(prefix="/api/birthday/internal/dev", tags=["birthday-dev-auth"])

_SUPPLIER_PORTAL_PERMISSIONS = ["birthday.portal.access", "birthday.portal.respond"]


def _require_dev_mode() -> None:
    settings = get_settings()
    if settings.app_env == "production":
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Not found"
        )  # 404, not 403 — this route must not even be discoverable in production


class DevSupplierPersona(BaseModel):
    supplier_user_id: int
    supplier_id: int
    email: str
    full_name: str
    supplier_name: str


class DevSupplierLoginRequest(BaseModel):
    supplier_user_id: int


class DevSupplierLoginResponse(BaseModel):
    access_token: str


@router.get("/supplier-users", response_model=list[DevSupplierPersona])
def list_dev_supplier_personas() -> list[DevSupplierPersona]:
    _require_dev_mode()
    db = SessionLocal()
    try:
        # Only ACTIVE personas are offered — mirrors production, where an
        # inactive SupplierUser cannot authenticate at all. Newly created
        # SupplierUsers are ACTIVE by default, so they appear here
        # immediately without any extra provisioning step.
        rows = db.execute(
            select(SupplierUser).where(SupplierUser.status == "ACTIVE")
        ).scalars().all()
        return [
            DevSupplierPersona(
                supplier_user_id=row.id,
                supplier_id=row.supplier_id,
                email=row.email,
                full_name=row.full_name or row.email,
                supplier_name=row.supplier.name if row.supplier else "",
            )
            for row in rows
        ]
    finally:
        db.close()


@router.post("/supplier-login", response_model=DevSupplierLoginResponse)
def dev_supplier_login(payload: DevSupplierLoginRequest) -> DevSupplierLoginResponse:
    """Mints a dev-signed token carrying the caller-chosen persona's own
    supplier_id — resolved from the SupplierUser row, never accepted
    directly from the request body."""
    _require_dev_mode()
    settings = get_settings()
    db = SessionLocal()
    try:
        supplier_user = db.get(SupplierUser, payload.supplier_user_id)
        if supplier_user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Supplier user not found")
        if supplier_user.status != "ACTIVE":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Supplier user is inactive")

        now = datetime.now(UTC)
        claims = {
            "sub": str(supplier_user.id),
            "iat": now,
            "exp": now + timedelta(hours=8),
            "iss": "dijione-dev-identity",
            "is_active": True,
            "full_name": supplier_user.full_name or supplier_user.email,
            "email": supplier_user.email,
            "platform_role": "PLATFORM_USER",
            "platform_permissions": [],
            "module_roles": {
                MODULE_BIRTHDAY: {
                    "role": BirthdayRole.BIRTHDAY_SUPPLIER.value,
                    "client_id": None,
                    "client_ids": None,
                    "permissions": _SUPPLIER_PORTAL_PERMISSIONS,
                }
            },
            "supplier": {
                "supplier_id": supplier_user.supplier_id,
                "supplier_user_id": supplier_user.id,
            },
        }
        token = jwt.encode(claims, settings.jwt_dev_secret, algorithm=settings.jwt_algorithm)
        return DevSupplierLoginResponse(access_token=token)
    finally:
        db.close()
