"""Birthday Supplier Portal — identity resolution + session-token minting.

Two responsibilities, shared by both auth modes:

* :func:`resolve_supplier_user` — verified Entra claims -> an ACTIVE
  ``SupplierUser`` row, or a fail-closed refusal. NEVER auto-creates a
  SupplierUser: a Microsoft account / B2B guest that has not been
  explicitly registered by an internal admin gets no Birthday access.
* :func:`mint_supplier_session_token` — the DijiOne-format HS256 token the
  supplier portal already consumes (``get_supplier_scope`` in
  ``app/api/deps.py``), with the ``supplier`` claim resolved server-side
  from the SupplierUser row.

The dev persona provider (``app/api/routes/dev_auth.py``) and the Entra
flow (``app/api/routes/supplier_auth_entra.py``) both end here, so the
authorization boundary is identical regardless of how identity was proven.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jose import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import MODULE_BIRTHDAY, BirthdayRole
from app.models.supplier_user import SupplierUser

_SUPPLIER_PORTAL_PERMISSIONS = ("birthday.portal.access", "birthday.portal.respond")
_SESSION_TTL = timedelta(hours=8)


class SupplierAccessRefusedError(Exception):
    """The verified identity does not map to an ACTIVE SupplierUser."""

    #: A single generic message — never disclose which of "unknown identity"
    #: / "inactive" / "no such supplier" applied.
    GENERIC = "Your account is not authorised for the DijiBirthday supplier portal."

    def __init__(self, message: str = GENERIC) -> None:
        super().__init__(message)


def _email_from_claims(claims: dict) -> str | None:
    """Best verified email for a member OR B2B guest.

    A B2B guest's ``preferred_username`` / ``upn`` is often the rewritten
    ``alice_contoso.com#EXT#@dijitalteam.onmicrosoft.com`` form — NOT an
    email — so those are only trusted when they actually look like a plain
    address. The ``email`` optional claim (when present) is preferred.
    """
    email = claims.get("email")
    if isinstance(email, str) and "@" in email and "#EXT#" not in email:
        return email.strip().lower()
    for key in ("preferred_username", "upn"):
        value = claims.get(key)
        if isinstance(value, str) and "@" in value and "#EXT#" not in value:
            return value.strip().lower()
    return None


def resolve_supplier_user(db: Session, claims: dict) -> SupplierUser:
    """Return the ACTIVE ``SupplierUser`` for a verified Entra id_token's
    claims, linking ``entra_object_id`` on first match by email. Raises
    :class:`SupplierAccessRefusedError` (fail closed) for anything else.
    """
    oid = claims.get("oid") or claims.get("sub")
    if not oid:
        raise SupplierAccessRefusedError()

    # 1. durable key — the stable Microsoft identity, once linked.
    row = db.execute(
        select(SupplierUser).where(SupplierUser.entra_object_id == oid)
    ).scalars().first()

    # 2. first sign-in — match on verified email, then stamp the oid so
    #    every subsequent login takes path 1 (email changes won't unlink).
    if row is None:
        email = _email_from_claims(claims)
        if email is None:
            raise SupplierAccessRefusedError()
        row = db.execute(
            select(SupplierUser).where(func.lower(SupplierUser.email) == email)
        ).scalars().first()
        if row is None:
            raise SupplierAccessRefusedError()
        if row.entra_object_id is None:
            row.entra_object_id = oid
            row.linked_at = datetime.now(UTC)
            db.commit()

    if row.status != "ACTIVE":
        raise SupplierAccessRefusedError()
    return row


def record_supplier_login(db: Session, supplier_user: SupplierUser) -> None:
    """Stamp ``last_login_at`` on a successful session mint (Phase 1 §1.6)
    — used by both the Entra flow and the dev persona picker."""
    supplier_user.last_login_at = datetime.now(UTC)
    if supplier_user.linked_at is None and supplier_user.entra_object_id is not None:
        supplier_user.linked_at = supplier_user.last_login_at
    db.commit()


def mint_supplier_session_token(supplier_user: SupplierUser) -> str:
    """The DijiOne-format supplier session token — identical shape whether
    identity came from the dev persona picker or Entra. ``supplier`` is
    taken from the row, never from any request input."""
    settings = get_settings()
    now = datetime.now(UTC)
    claims = {
        "sub": str(supplier_user.id),
        "iat": now,
        "exp": now + _SESSION_TTL,
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
                "permissions": list(_SUPPLIER_PORTAL_PERMISSIONS),
            }
        },
        "supplier": {
            "supplier_id": supplier_user.supplier_id,
            "supplier_user_id": supplier_user.id,
        },
    }
    return jwt.encode(claims, settings.jwt_dev_secret, algorithm=settings.jwt_algorithm)
