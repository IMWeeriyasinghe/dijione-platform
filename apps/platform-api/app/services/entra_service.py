"""Resolve a verified Microsoft Entra identity to a DijiOne ``User``.

First-login policy (Pre-DEV Execution Plan §7c, option C): an Entra identity
with no existing DijiOne user is **auto-created inactive** — login is then
refused (403) until a platform admin activates the account and assigns
access in the Admin Center. This gives the team self-service onboarding
without granting any standing access to the whole tenant.

Matching order:
  1. ``users.entra_object_id`` == the token's ``oid`` (stable, preferred)
  2. ``users.email`` == the token's email/preferred_username (first login —
     stamps ``entra_object_id`` so subsequent logins take path 1)
  3. neither -> create ``is_active=False``
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import PlatformRole
from app.models.user import User


class EntraLoginRefusedError(Exception):
    """The Entra identity resolved to a DijiOne user that is not active."""

    def __init__(self, *, created: bool) -> None:
        self.created = created
        super().__init__(
            "Your account is not yet active in DijiOne. "
            + ("It has just been created — " if created else "")
            + "ask a platform administrator to activate it and assign access."
        )


def _email_from_claims(claims: dict) -> str | None:
    for key in ("email", "preferred_username", "upn"):
        value = claims.get(key)
        if value and "@" in value:
            return value.lower()
    return None


def resolve_entra_user(db: Session, claims: dict) -> User:
    """Return the active DijiOne ``User`` for a verified Entra id_token's
    claims. Raises ``EntraLoginRefusedError`` if the user exists but is
    inactive, or was just auto-created."""
    oid = claims.get("oid") or claims.get("sub")
    if not oid:
        raise ValueError("Entra token has no oid/sub claim")
    email = _email_from_claims(claims)
    name = claims.get("name") or email or oid

    user = db.execute(select(User).where(User.entra_object_id == oid)).scalars().first()

    created = False
    if user is None and email is not None:
        user = db.execute(select(User).where(User.email == email)).scalars().first()
        if user is not None:
            user.entra_object_id = oid
            user.identity_provider = "ENTRA"

    if user is None:
        if email is None:
            raise ValueError("Entra token has no usable email claim")
        user = User(
            email=email,
            full_name=name,
            platform_role=PlatformRole.PLATFORM_USER.value,
            entra_object_id=oid,
            identity_provider="ENTRA",
            is_active=False,
        )
        db.add(user)
        db.flush()
        created = True

    if not user.is_active:
        db.commit()  # persist the just-created / newly-linked row
        raise EntraLoginRefusedError(created=created)

    user.last_login_at = datetime.now(UTC)
    if user.identity_provider != "ENTRA":
        user.identity_provider = "ENTRA"
    db.commit()
    return user
