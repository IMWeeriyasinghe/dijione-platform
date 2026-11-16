"""Per-user access versions.

Every change that can alter what a person may do bumps ``users.access_version``
in the same transaction as the change. A session token records the version it
was issued under (``av``); applications reject a token older than the person's
current version, and the person's client refreshes to obtain current roles.

The bump is done here, in one SQLAlchemy ``before_flush`` listener, rather than at
each call site, so a future code path that changes access cannot forget it.
Changes made by Alembic migrations do not go through the session and must call
``bump_all`` themselves.

Concurrency: the bump is ``UPDATE users SET access_version = access_version + 1``.
The row lock serialises concurrent changes to one person, and no clock is read,
so there is no time boundary to get wrong. A version only ever increases.
"""

from __future__ import annotations

from sqlalchemy import event, inspect, select, update
from sqlalchemy.orm import Session

from app.models.access_group import (
    AccessGroup,
    GroupModuleClientScope,
    GroupModuleRole,
    UserGroupMembership,
)
from app.models.module import ApplicationModule
from app.models.module_baseline import ModuleBaselineRole
from app.models.role import Permission, Role, RolePermission
from app.models.user import User, UserModuleRole
from app.models.user_module_client_scope import UserModuleClientScope

# User columns whose change alters access (or how access is derived).
_USER_ACCESS_COLUMNS = {"is_active", "platform_role", "internal_employee", "identity_provider", "entra_object_id"}
# A change to any of these affects every user.
_GLOBAL_MODELS = (ModuleBaselineRole, Role, RolePermission, Permission)
_SESSION_KEY = "access_version_pending"


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
            users.add(obj.user_id)
        elif isinstance(obj, UserGroupMembership):
            users.add(obj.user_id)
        elif isinstance(obj, UserModuleClientScope):
            owner = obj.user_module_role_id and connection.execute(
                select(UserModuleRole.user_id).where(UserModuleRole.id == obj.user_module_role_id)
            ).scalar()
            if owner:
                users.add(owner)
        elif isinstance(obj, GroupModuleRole):
            groups.add(obj.access_group_id)
        elif isinstance(obj, GroupModuleClientScope):
            owner = obj.group_module_role_id and connection.execute(
                select(GroupModuleRole.access_group_id).where(GroupModuleRole.id == obj.group_module_role_id)
            ).scalar()
            if owner:
                groups.add(owner)
        elif isinstance(obj, AccessGroup):
            if obj in session.deleted or (not is_new and _changed(obj, {"status"})):
                groups.add(obj.id)
        elif isinstance(obj, User):
            if not is_new and _changed(obj, _USER_ACCESS_COLUMNS):
                users.add(obj.id)
        elif isinstance(obj, ApplicationModule):
            if not is_new and _changed(obj, {"enabled"}):
                everyone = True
        elif isinstance(obj, _GLOBAL_MODELS):
            everyone = True

    users |= _group_member_ids(connection, groups)
    return users, everyone


def _bump(session: Session, users: set[int], everyone: bool) -> None:
    connection = session.connection()
    stmt = update(User.__table__).values(access_version=User.__table__.c.access_version + 1)
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


def bump_all(connection) -> None:
    """For migrations and operational use: invalidate every session."""
    connection.execute(update(User.__table__).values(access_version=User.__table__.c.access_version + 1))


@event.listens_for(Session, "before_flush")
def _bump_access_versions(session: Session, _flush_context, _instances) -> None:
    if not (session.new or session.dirty or session.deleted):
        return
    users, everyone = affected_users(session)
    if users or everyone:
        _bump(session, users, everyone)
