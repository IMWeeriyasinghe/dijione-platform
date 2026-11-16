"""View-as: a SUPER_ADMIN's strictly read-only simulation of one internal employee.

The token is signed for the *employee* (``sub`` and every authorization claim are theirs), so each
application authorizes a request exactly as it would the employee. It is marked
``actor_type = view_as``: platform-api refuses it everywhere except the few read-only endpoints a
shell needs to draw itself, so it can be neither refreshed nor exchanged for a staff session, and
the shared authorization layer (``auth_client_py``) allows it only on routes classified READ.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import PlatformRole
from app.core.security import issue_view_as_token
from app.models.user import User
from app.models.view_as_session import ViewAsSession
from app.services.audit_service import AuditService
from app.services.authorization_service import AuthorizationService
from app.services.claims_service import build_claims

PERMISSION = "platform.admin.view_as"


class ViewAsError(Exception):
    status_code = 400


class ViewAsForbidden(ViewAsError):
    status_code = 403


class ViewAsNotFound(ViewAsError):
    status_code = 404


class ViewAsInvalid(ViewAsError):
    """A presented View-as token is no longer valid (ended, expired, or the people involved changed)."""

    status_code = 401


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


@dataclass(frozen=True)
class StartedSession:
    session: ViewAsSession
    token: str
    target: User


class ViewAsService:
    def __init__(self, db: Session):
        self.db = db
        self.authz = AuthorizationService(db)
        self.audit = AuditService(db)

    def _require_authorised(self, actor: User) -> None:
        if actor.platform_role != PlatformRole.SUPER_ADMIN.value or PERMISSION not in self.authz.platform_permissions(actor):
            raise ViewAsForbidden("View-as requires the Super Admin role and the View As User permission")

    def start(self, actor: User, target_user_id: int) -> StartedSession:
        if not get_settings().view_as_enabled:
            raise ViewAsNotFound("View as is not enabled in this environment")
        self._require_authorised(actor)
        target = self.db.get(User, target_user_id)
        # The caller is a Super Admin who can already see this user in the Admin Center, so naming the
        # reason reveals nothing new. The conditions themselves are unchanged.
        if target is None:
            raise ViewAsNotFound("That user does not exist.")
        if target.id == actor.id:
            raise ViewAsNotFound("You cannot view as yourself.")
        if not target.is_active:
            raise ViewAsNotFound("That user is inactive. View as is available for active internal employees only.")
        if not target.internal_employee and target.entra_object_id is not None:
            raise ViewAsNotFound(
                "That user's Microsoft identity was not verified as an internal employee (for example a guest "
                "account), so View as is not available for them."
            )
        if not self.authz.identity_verified(target):
            raise ViewAsNotFound(
                "That user's identity is not verified yet. Use Verify with directory on their profile (or it is "
                "verified at their first Microsoft sign-in); View as becomes available then."
            )
        if not self.authz.is_eligible_employee(target):
            raise ViewAsNotFound(
                "That user is not matched to an employee record in BambooHR, so View as is not available. "
                "Their access can still be previewed; HR reconciliation is needed."
            )

        now = datetime.now(UTC)
        for previous in self.db.execute(
            select(ViewAsSession).where(ViewAsSession.admin_user_id == actor.id, ViewAsSession.ended_at.is_(None))
        ).scalars():
            previous.ended_at, previous.end_reason = now, "replaced"
            self.audit.log(
                actor_id=actor.id, action="view_as.ended", entity_type="ViewAsSession", entity_id=previous.id,
                subject_user_id=previous.target_user_id,
                new_state={"session_id": previous.public_id, "reason": "replaced"},
            )

        # Version first, then claims (see app/api/routes/auth.py::issue_user_session).
        target_version = self.db.execute(
            select(User.access_version).where(User.id == target.id).execution_options(populate_existing=True)
        ).scalar_one()
        actor_version = self.db.execute(
            select(User.access_version).where(User.id == actor.id).execution_options(populate_existing=True)
        ).scalar_one()
        expires = now + timedelta(minutes=get_settings().view_as_minutes)
        session = ViewAsSession(
            public_id=str(uuid.uuid4()), admin_user_id=actor.id, target_user_id=target.id,
            started_at=now, expires_at=expires,
        )
        self.db.add(session)
        self.db.flush()
        claims = build_claims(target, self.db)
        token = issue_view_as_token(
            target.id,
            **claims,
            av=target_version,
            exp=expires,
            view_as={
                "session_id": session.public_id, "actor_id": actor.id, "actor_name": actor.full_name,
                "actor_av": actor_version,
            },
        )
        self.audit.log(
            actor_id=actor.id, action="view_as.started", entity_type="ViewAsSession", entity_id=session.id,
            subject_user_id=target.id,
            new_state={"session_id": session.public_id, "target_user_id": target.id, "expires_at": expires.isoformat()},
        )
        self.db.commit()
        return StartedSession(session=session, token=token, target=target)

    def end(self, actor: User, public_id: str, *, reason: str = "ended") -> ViewAsSession:
        session = self.db.execute(select(ViewAsSession).where(ViewAsSession.public_id == public_id)).scalar_one_or_none()
        if session is None or session.admin_user_id != actor.id:
            raise ViewAsNotFound("No such View-as session")
        if session.ended_at is None:
            session.ended_at, session.end_reason = datetime.now(UTC), reason
            self.audit.log(
                actor_id=actor.id, action="view_as.ended", entity_type="ViewAsSession", entity_id=session.id,
                subject_user_id=session.target_user_id, new_state={"session_id": public_id, "reason": reason},
            )
            self.db.commit()
        return session

    def resolve(self, payload: dict) -> tuple[User, ViewAsSession]:
        """Check a presented View-as token against the database; return (target, session)."""
        claim = payload.get("view_as")
        if not isinstance(claim, dict) or not isinstance(claim.get("session_id"), str):
            raise ViewAsInvalid("Invalid View-as session")
        session = self.db.execute(
            select(ViewAsSession).where(ViewAsSession.public_id == claim["session_id"])
        ).scalar_one_or_none()
        try:
            target_id = int(payload["sub"])
            actor_id = int(claim["actor_id"])
        except (KeyError, TypeError, ValueError):
            raise ViewAsInvalid("Invalid View-as session") from None
        if (
            session is None
            or session.ended_at is not None
            or _aware(session.expires_at) <= datetime.now(UTC)
            or session.target_user_id != target_id
            or session.admin_user_id != actor_id
        ):
            raise ViewAsInvalid("This View-as session has ended")
        target, actor = self.db.get(User, target_id), self.db.get(User, actor_id)
        if target is None or not target.is_active or actor is None or not actor.is_active:
            raise ViewAsInvalid("This View-as session has ended")
        try:
            self._require_authorised(actor)
        except ViewAsForbidden:
            raise ViewAsInvalid("This View-as session has ended") from None
        if int(payload.get("av", 0)) < target.access_version or int(claim.get("actor_av", 0)) < actor.access_version:
            raise ViewAsInvalid("This View-as session has ended because access changed")
        return target, session
