"""Per-user access versions.

Every change that can alter what a person may do bumps ``users.access_version``
in the same transaction as the change. A session token records the version it
was issued under (``av``); applications reject a token older than the person's
current version, and the person's client refreshes to obtain current roles.

The bump is done here, in one SQLAlchemy ``before_flush`` listener, rather than at
each call site, so a future code path that changes access cannot forget it.
Changes made by Alembic migrations do not go through the session and must call
``bump_all`` themselves.

Concurrency: the bump is one atomic UPDATE, so the row lock serialises concurrent changes
to one person. A version only ever increases.

Surviving a database restore: the new value is ``max(old + 1, now_in_unix_seconds)``. The
``+ 1`` is what orders changes; the clock is only a floor. If the database is restored to an
earlier state, its counters go back, and a plain ``+ 1`` could reissue a number that tokens
issued during the lost interval already carry, so a genuine revocation would not revoke them.
Because every bump is at least the time it happened, any bump made after a restore is higher
than anything issued before it (as long as the clock has not gone backwards past the backup).
After a restore also run ``python -m app.services.access_version``: it raises every user above
everything issued before, which ends every older session.
"""

from __future__ import annotations

import time

from sqlalchemy import case, event, inspect, select, update
from sqlalchemy.orm import Session

from app.models.access_group import (
    AccessGroup,
    GroupModuleClientScope,
    GroupModuleRole,
    UserGroupMembership,
)
from app.models.application_access import ApplicationAccessSuspension, ApplicationAdministrator
from app.models.module import ApplicationModule
from app.models.module_baseline import ModuleBaselineRole
from app.models.role import Permission, Role, RolePermission
from app.models.user import User, UserModuleRole
from app.models.user_module_client_scope import UserModuleClientScope

# User columns whose change alters access (or how access is derived).
_USER_ACCESS_COLUMNS = {
    "is_active", "platform_role", "internal_employee", "identity_provider", "entra_object_id", "email",
    "employee_record_status",  # decides eligibility: default access and appointments
}
# A change to any of these affects every user.
_GLOBAL_MODELS = (ModuleBaselineRole, Role, RolePermission, Permission)
_SESSION_KEY = "access_version_pending"
# session.info key: users whose access may have changed in the open transaction (read by
# app.services.access_notifications at commit, cleared when the transaction ends).
ACCESS_CHANGE_KEY = "access_change_pending"


def _changed(obj, columns: set[str]) -> bool:
    state = inspect(obj)
    return any(state.attrs[name].history.has_changes() for name in columns if name in state.attrs)


def _group_member_ids(connection, group_ids: set[int]) -> set[int]:
    if not group_ids:
        return set()
    rows = connection.execute(
        select(UserGroupMembership.user_id).where(UserGroupMembership.access_group_id.in_(group_ids))
    )
    return {r[0] for r in rows}


def _was(obj, attribute: str) -> list:
    """Values an attribute held before this flush (for a row moved from one owner to another)."""
    state = inspect(obj)
    return [v for v in state.attrs[attribute].history.deleted if v is not None]


def _user_of_role(role) -> int | None:
    """The user a direct assignment belongs to, whether the foreign key or only the
    relationship has been set so far."""
    return role.user_id if role.user_id is not None else (role.user.id if role.user is not None else None)


def _group_of_role(role) -> int | None:
    return (
        role.access_group_id
        if role.access_group_id is not None
        else (role.access_group.id if role.access_group is not None else None)
    )


def _owner(connection, wanted, key, value):
    return connection.execute(select(wanted).where(key == value)).scalar() if value is not None else None


def affected_users(session: Session) -> tuple[set[int], bool]:
    """(user ids whose access may change in this flush, whether everyone's may)."""
    connection = session.connection()
    users: set[int] = set()
    groups: set[int] = set()
    everyone = False

    # Objects merely touched (flagged dirty with no net change) change nothing.
    modified = [o for o in session.dirty if session.is_modified(o)]
    for obj in [*session.new, *modified, *session.deleted]:
        is_new = obj in session.new
        if isinstance(obj, UserModuleRole):
            users.add(_user_of_role(obj))
            users.update(_was(obj, "user_id") if not is_new else [])
        elif isinstance(obj, UserGroupMembership):
            users.add(obj.user_id)
            users.update(_was(obj, "user_id") if not is_new else [])
        elif isinstance(obj, UserModuleClientScope):
            role = obj.user_module_role
            users.add(_user_of_role(role) if role is not None else _owner(connection, UserModuleRole.user_id,
                                                                         UserModuleRole.id, obj.user_module_role_id))
        elif isinstance(obj, GroupModuleRole):
            groups.add(_group_of_role(obj))
            groups.update(_was(obj, "access_group_id") if not is_new else [])
        elif isinstance(obj, GroupModuleClientScope):
            role = obj.group_module_role
            groups.add(_group_of_role(role) if role is not None else _owner(connection, GroupModuleRole.access_group_id,
                                                                           GroupModuleRole.id, obj.group_module_role_id))
        elif isinstance(obj, ApplicationAdministrator | ApplicationAccessSuspension):
            users.add(obj.user_id)
            users.update(_was(obj, "user_id") if not is_new else [])
        elif isinstance(obj, AccessGroup):
            # group_type decides whether the group's grants are mandatory (SYSTEM: not suspendable).
            if obj in session.deleted or (not is_new and _changed(obj, {"status", "group_type"})):
                groups.add(obj.id)
        elif isinstance(obj, User):
            if not is_new and _changed(obj, _USER_ACCESS_COLUMNS):
                users.add(obj.id)
        elif isinstance(obj, ApplicationModule):
            # Enabling or disabling a module, renaming its key, or removing it changes every
            # default grant and every module_roles claim built from it.
            if obj in session.deleted or (not is_new and _changed(obj, {"enabled", "key"})):
                everyone = True
        elif isinstance(obj, _GLOBAL_MODELS):
            everyone = True
    users.discard(None)  # a brand-new user or group has no sessions and no members yet
    groups.discard(None)

    users |= _group_member_ids(connection, groups)
    return users, everyone


def _next_version():
    """``max(access_version + 1, now)`` in a form every supported database accepts."""
    column = User.__table__.c.access_version
    floor = int(time.time())
    return case((column + 1 > floor, column + 1), else_=floor)


def _bump(session: Session, users: set[int], everyone: bool) -> None:
    connection = session.connection()
    stmt = update(User.__table__).values(access_version=_next_version())
    if not everyone:
        users = {u for u in users if u is not None}
        if not users:
            return
        stmt = stmt.where(User.__table__.c.id.in_(users))
    connection.execute(stmt)
    # Instances already loaded in this session must not keep a stale counter.
    for obj in list(session.identity_map.values()):
        if isinstance(obj, User) and (everyone or obj.id in users) and "access_version" not in inspect(obj).unloaded:
            session.expire(obj, ["access_version"])


def bump_all(connection) -> int:
    """For migrations and operational use (notably after a database restore): invalidate
    every session. Returns the number of users raised."""
    return connection.execute(update(User.__table__).values(access_version=_next_version())).rowcount


if __name__ == "__main__":  # python -m app.services.access_version  (run after restoring a backup)
    from app.db.session import SessionLocal

    with SessionLocal() as _session, _session.begin():
        print(f"access_version raised for {bump_all(_session.connection())} users; all earlier sessions are now revoked")


@event.listens_for(Session, "before_flush")
def _bump_access_versions(session: Session, _flush_context, _instances) -> None:
    if not (session.new or session.dirty or session.deleted):
        return
    users, everyone = affected_users(session)
    # Shared with access_notifications: the same "whose access may have changed" answer,
    # accumulated across every flush of the transaction and acted on at commit.
    pending = session.info.setdefault(ACCESS_CHANGE_KEY, {"users": set(), "everyone": False, "new_users": []})
    pending["users"] |= users
    pending["everyone"] = pending["everyone"] or everyone
    pending["new_users"].extend(o for o in session.new if isinstance(o, User))
    if users or everyone:
        _bump(session, users, everyone)
