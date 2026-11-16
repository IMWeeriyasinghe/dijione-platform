"""Protected administrators: a SUPER_ADMIN privilege that DijiOne itself cannot remove.

Policy rows live in ``protected_admins`` (written by a migration only). Enforcement is a
SQLAlchemy ``before_flush`` listener, so every code path that changes a user through the ORM is
covered with no per-endpoint check to forget, and it runs inside the same transaction as the
change it refuses. It refuses, for the protected user, any flush that would:

* change the platform role away from SUPER_ADMIN;
* deactivate the account;
* delete the account;
* change the e-mail address or re-bind the Entra identity (first binding is allowed);

and, for the policy itself, any flush that edits or deletes a policy row, deletes or renames the
SUPER_ADMIN role, or detaches a permission from it.

``assert_may_change`` and ``record_blocked`` let the admin service refuse earlier, with a clear
message and an audit entry, before the guard is reached. ``converge`` is the one place that moves
a protected account *towards* its required state (sign-in and migrations call it).

Bulk Core statements and direct SQL do not pass through the ORM. That is the intended
infrastructure-level recovery path (see docs/platform/protected-super-admin.md); no application
endpoint issues one.
"""

from __future__ import annotations

import logging

from sqlalchemy import event, inspect, text
from sqlalchemy.orm import Session

from app.core.constants import PlatformRole
from app.models.protected_admin import ProtectedAdmin
from app.models.role import Role, RolePermission
from app.models.user import User

logger = logging.getLogger(__name__)

PROTECTED_ROLE = PlatformRole.SUPER_ADMIN.value
MESSAGE = "This account's Super Admin privilege is protected and cannot be removed by other administrators."


class ProtectedAdminError(Exception):
    """A change that would remove or weaken a protected administrator's access."""


def _policies(connection) -> list[tuple[str, str | None]]:
    rows = connection.execute(text("SELECT email, entra_object_id FROM protected_admins"))
    return [((email or "").lower(), oid) for email, oid in rows]


def _old(obj, attribute: str):
    """The value an attribute held in the database before this flush. Read from the row itself:
    the in-memory history is empty for an attribute that was expired when it was assigned."""
    if obj.id is None:
        return None
    connection = inspect(obj).session.connection()
    return connection.execute(text(f"SELECT {attribute} FROM users WHERE id = :i"), {"i": obj.id}).scalar()


def _is_protected(policies, *, email: str | None, oid: str | None) -> bool:
    email = (email or "").lower()
    return any(email == p_email or (oid is not None and oid == p_oid) for p_email, p_oid in policies)


def is_protected_user(session: Session, user: User) -> bool:
    return _is_protected(_policies(session.connection()), email=_old(user, "email"), oid=_old(user, "entra_object_id"))


def is_protected_email(session: Session, email: str) -> bool:
    return _is_protected(_policies(session.connection()), email=email, oid=None)


def _violations(obj: User, policies, *, deleted: bool) -> list[str]:
    if not _is_protected(policies, email=_old(obj, "email"), oid=_old(obj, "entra_object_id")):
        return []
    found: list[str] = []
    if deleted:
        return ["delete the protected account"]
    state = inspect(obj).attrs
    if state["platform_role"].history.has_changes() and obj.platform_role != PROTECTED_ROLE:
        found.append("change the platform role")
    if state["is_active"].history.has_changes() and not obj.is_active:
        found.append("deactivate the account")
    if state["email"].history.has_changes():
        found.append("change the e-mail address")
    if state["entra_object_id"].history.has_changes() and _old(obj, "entra_object_id") is not None:
        found.append("change the identity binding")
    return found


def _check_session(session: Session) -> None:
    policies = _policies(session.connection())
    for obj in [*session.dirty, *session.deleted]:
        if isinstance(obj, User):
            problems = _violations(obj, policies, deleted=obj in session.deleted)
            if problems:
                raise ProtectedAdminError(f"{MESSAGE} Refused: {', '.join(problems)}.")
        elif isinstance(obj, ProtectedAdmin):
            raise ProtectedAdminError("The protected administrator policy cannot be changed through DijiOne.")
        elif isinstance(obj, Role) and (obj in session.deleted or inspect(obj).attrs["key"].history.has_changes()):
            committed = session.connection().execute(
                text("SELECT key FROM roles WHERE id = :i AND module_key IS NULL"), {"i": obj.id}
            ).scalar()
            if committed == PROTECTED_ROLE:
                raise ProtectedAdminError("The SUPER_ADMIN role cannot be renamed or deleted.")
        elif isinstance(obj, RolePermission) and obj in session.deleted:
            role = session.get(Role, obj.role_id)
            if role is not None and role.key == PROTECTED_ROLE and role.module_key is None:
                raise ProtectedAdminError("A permission cannot be removed from the SUPER_ADMIN role.")
    for obj in session.new:
        if isinstance(obj, ProtectedAdmin):
            raise ProtectedAdminError("The protected administrator policy cannot be changed through DijiOne.")


def assert_may_change(session: Session, user: User, *, deactivate: bool = False, new_role: str | None = None) -> None:
    """Refuse early, with an explanation, an action aimed at a protected user."""
    if not is_protected_user(session, user):
        return
    if deactivate:
        raise ProtectedAdminError(f"{MESSAGE} It cannot be deactivated.")
    if new_role is not None and new_role != PROTECTED_ROLE:
        raise ProtectedAdminError(f"{MESSAGE} Its platform role cannot be changed.")


def converge(session: Session, user: User) -> bool:
    """Bring a protected account to its required state and record its Entra binding.

    Runs on sign-in, never on request of another administrator. Moves only towards the
    required state (SUPER_ADMIN, active), so the guard allows it. Returns True if it changed anything.
    """
    connection = session.connection()
    if not _is_protected(_policies(connection), email=user.email, oid=user.entra_object_id):
        return False
    changed = False
    if user.platform_role != PROTECTED_ROLE:
        user.platform_role = PROTECTED_ROLE
        changed = True
    if not user.is_active:
        user.is_active = True
        changed = True
    if user.entra_object_id:
        connection.execute(
            text("UPDATE protected_admins SET entra_object_id = :oid WHERE lower(email) = :email AND entra_object_id IS NULL"),
            {"oid": user.entra_object_id, "email": (user.email or "").lower()},
        )
    return changed


@event.listens_for(Session, "before_flush")
def _protected_admin_guard(session: Session, _flush_context, _instances) -> None:
    if not (session.new or session.dirty or session.deleted):
        return
    _check_session(session)
