"""Resolve a verified Microsoft Entra identity to a DijiOne ``User``.

First-login policy (automatic onboarding, 2026-11): a proven internal Member of our
tenant (``is_internal_employee``: our ``tid``, our identity provider, ``acct=0``, no
``#ext#``, an internal-domain address; never the domain alone) who has no DijiOne
user is created **active, as a Platform User** with nothing else granted. Every
other identity (a Guest, another tenant, an unproven member) is created inactive
and refused until an administrator decides. Default employee access (DijiAtWork)
is separate: it still needs a matching employee record (``is_eligible_employee``).

An inactive account is activated automatically only when it is a pending
self-sign-in row: created by an Entra sign-in (provenance audit
``entra-signin-created:<oid>``), never signed in, and never activated or
deactivated by anyone. Anything else (including rows created by the earlier
policy, which wrote no provenance audit) stays inactive: fail closed.

Matching order:
  1. ``users.entra_object_id`` == the token's ``oid`` (stable, preferred)
  2. ``users.email`` == the token's email/preferred_username, only for a proven
     internal employee and an account not yet linked to any Entra object
  3. neither -> create (active for a proven internal Member, else inactive)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import PlatformRole
from app.models.audit_log import AuditLog
from app.models.user import User
from app.services import protected_admin
from app.services.audit_service import AuditService
from app.services.directory_service import check_at_sign_in

logger = logging.getLogger("platform-api.entra")


class EntraLoginRefusedError(Exception):
    """The Entra identity resolved to a DijiOne user that is not active."""

    def __init__(self, *, created: bool) -> None:
        self.created = created
        super().__init__(
            "Your account is not yet active in DijiOne. "
            + ("It has just been created — " if created else "")
            + "ask a platform administrator to activate it and assign access."
        )


class EntraIdentityConflictError(EntraLoginRefusedError):
    """The identity's email belongs to an account this identity may not claim."""

    def __init__(self) -> None:
        super().__init__(created=False)
        self.args = (
            "A DijiOne account exists for this email address but could not be linked to this Microsoft sign-in. "
            "Ask a platform administrator to check the account in DijiOne Admin.",
        )


def _email_from_claims(claims: dict) -> str | None:
    for key in ("email", "preferred_username", "upn"):
        value = claims.get(key)
        if value and "@" in value:
            return value.lower()
    return None


def is_internal_employee(claims: dict) -> bool:
    """True only on affirmative proof of tenant membership. A single-tenant issuer
    does not exclude B2B guests, and a missing claim proves nothing, so the app
    registration must emit the optional `acct` claim (0 = member, 1 = guest)."""
    settings = get_settings()
    domains = {d.strip().lower() for d in settings.entra_internal_email_domains.split(",") if d.strip()}
    email = _email_from_claims(claims)
    if not domains or email is None or email.rsplit("@", 1)[1] not in domains:
        return False
    tenant = settings.entra_tenant_id
    if not tenant or claims.get("tid") != tenant:
        return False
    # Microsoft omits ``idp`` when the user authenticated with the token issuer itself; the issuer
    # is then the identity provider. Either way it must be our own tenant, never a foreign one.
    own = {f"https://sts.windows.net/{tenant}/", settings.entra_issuer}
    if (claims.get("idp") or claims.get("iss")) not in own:
        return False
    if claims.get("acct") not in (0, "0"):
        return False
    names = [claims.get(k) for k in ("email", "preferred_username", "upn")]
    return not any("#ext#" in n.lower() for n in names if isinstance(n, str))


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
        # Stored addresses may differ in case from the Entra claim; a case-sensitive
        # miss here would create a second, inactive account for the same person.
        matches = db.execute(select(User).where(func.lower(User.email) == email)).scalars().all()
        if len(matches) > 1:
            logger.warning("Entra sign-in refused: %d accounts share this email ignoring case", len(matches))
            raise EntraIdentityConflictError
        user = matches[0] if matches else None
        if user is not None:
            # An email claim is not an identity. Only a proven member of our tenant may
            # claim an account that has never been linked to another Entra object.
            if user.entra_object_id is not None:
                logger.warning("Entra sign-in refused: account %s is linked to another Entra identity", user.id)
                raise EntraIdentityConflictError
            if not is_internal_employee(claims):
                logger.warning("Entra sign-in refused: identity not proven internal, cannot claim account %s", user.id)
                raise EntraIdentityConflictError
            user.entra_object_id = oid
            user.identity_provider = "ENTRA"

    internal = is_internal_employee(claims)
    if user is None:
        if email is None:
            raise ValueError("Entra token has no usable email claim")
        user, created = _create_signin_user(db, oid=oid, email=email, name=name, active=internal)

    user.internal_employee = internal
    activated = False
    if internal and not user.is_active and _is_pending_self_signin(db, user, oid):
        user.is_active = True
        activated = True
    if created or activated:
        _audit_activation(db, user, oid=oid, created=created)
    if user.internal_employee:
        # A protected administrator's required state is re-applied at every verified sign-in.
        protected_admin.converge(db, user)
        # Default employee access also needs a matching employee record (BambooHR). A soft check:
        # it never blocks the sign-in, never revokes, and an unavailable HR source changes nothing.
        # A first sign-in waits briefly for an HR snapshot that is loading, never longer.
        check_at_sign_in(user, wait_seconds=FIRST_SIGNIN_HR_WAIT_SECONDS if (created or activated) else 0)

    if not user.is_active:
        db.commit()  # persist the just-created / newly-linked row
        raise EntraLoginRefusedError(created=created)

    user.last_login_at = datetime.now(UTC)
    if user.identity_provider != "ENTRA":
        user.identity_provider = "ENTRA"
    db.commit()
    return user


FIRST_SIGNIN_HR_WAIT_SECONDS = 5.0


def _created_event_id(oid: str) -> str:
    return f"entra-signin-created:{oid}"[:64]


def _create_signin_user(db: Session, *, oid: str, email: str, name: str, active: bool) -> tuple[User, bool]:
    """Create the account for a first sign-in, safely against a concurrent first sign-in of the same
    identity: the unique ``entra_object_id`` decides, and the loser reuses the winner's row."""
    try:
        with db.begin_nested():
            user = User(
                email=email, full_name=name, platform_role=PlatformRole.PLATFORM_USER.value,
                entra_object_id=oid, identity_provider="ENTRA", is_active=active,
            )
            db.add(user)
            db.flush()
        AuditService(db).log_once(
            event_id=_created_event_id(oid), actor_id=user.id, action="user.created", entity_type="User",
            entity_id=user.id, subject_user_id=user.id,
            new_state={"email": email, "platform_role": user.platform_role, "is_active": active,
                       "source": "ENTRA_SIGN_IN"},
        )
        return user, True
    except IntegrityError:
        existing = db.execute(select(User).where(User.entra_object_id == oid)).scalars().first()
        if existing is None:
            raise
        return existing, False


def _is_pending_self_signin(db: Session, user: User, oid: str) -> bool:
    """An inactive account created by an Entra sign-in that nobody has decided on yet. Without the
    provenance audit the origin is unknown, so the account stays inactive (fail closed)."""
    if user.identity_provider != "ENTRA" or user.entra_object_id != oid or user.last_login_at is not None:
        return False
    provenance = db.execute(
        select(AuditLog.id).where(AuditLog.event_id == _created_event_id(oid), AuditLog.subject_user_id == user.id)
    ).first()
    if provenance is None:
        return False
    decided = db.execute(
        select(AuditLog.id).where(
            AuditLog.subject_user_id == user.id, AuditLog.action.in_(("user.activated", "user.deactivated"))
        )
    ).first()
    return decided is None


def _audit_activation(db: Session, user: User, *, oid: str, created: bool) -> None:
    if not user.is_active:
        return
    AuditService(db).log_once(
        event_id=f"entra-signin-activated:{oid}"[:64], actor_id=user.id, action="user.activated",
        entity_type="User", entity_id=user.id, subject_user_id=user.id,
        previous_state={"is_active": False}, new_state={"is_active": True},
        metadata={"source": "AUTOMATIC_FIRST_SIGN_IN", "channel": "SYSTEM", "new_account": created},
    )
