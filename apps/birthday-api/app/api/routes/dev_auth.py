"""Dev-only supplier persona provider (Phase-Next §5/§6) — the local
stand-in for Microsoft Entra ID B2B guest auth in the supplier portal.

Reachable only when ``SUPPLIER_AUTH_MODE=dev`` (NOT keyed off app_env any
more): a hosted DEV that has switched to ``SUPPLIER_AUTH_MODE=entra``
404s these routes. Callers pick a seeded ``SupplierUser`` row and receive
a token whose ``supplier`` claim is resolved server-side from that row's
own ``supplier_id`` — a caller can select *which persona* to become,
never *which supplier_id* to claim. Both this path and the Entra flow end
at :func:`mint_supplier_session_token`, so the authorization/isolation
layer (``SupplierScope``, repository-level ``supplier_id`` scoping) is
identical regardless of how identity was proven.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.supplier_user import SupplierUser
from app.services.supplier_auth import mint_supplier_session_token

router = APIRouter(prefix="/api/birthday/internal/dev", tags=["birthday-dev-auth"])


def _require_dev_mode() -> None:
    if not get_settings().dev_supplier_auth_enabled:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Not found"
        )  # 404, not 403 — this route must not even be discoverable when SUPPLIER_AUTH_MODE=entra


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
    """Mints the shared supplier session token for the caller-chosen
    persona — supplier_id resolved from the SupplierUser row, never
    accepted from the request body."""
    _require_dev_mode()
    db = SessionLocal()
    try:
        supplier_user = db.get(SupplierUser, payload.supplier_user_id)
        if supplier_user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Supplier user not found")
        if supplier_user.status != "ACTIVE":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Supplier user is inactive")
        return DevSupplierLoginResponse(access_token=mint_supplier_session_token(supplier_user))
    finally:
        db.close()
