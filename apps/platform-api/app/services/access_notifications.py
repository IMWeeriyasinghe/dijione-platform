"""Access-change email notifications, queued in the same transaction as the change.

How it works
------------
1. ``access_version``'s ``before_flush`` listener already works out, for every flush, which
   people's access may have changed (direct and group assignments, memberships, group status,
   appointments, suspensions, default access, module enablement, the role catalog, and the
   user columns that decide eligibility). It records them in ``session.info``.
2. At commit (``before_commit``, still inside the transaction) this module recomputes each of
   those people's **effective** access with ``AuthorizationService`` and compares it with the
   snapshot they were last notified about (``user_access_snapshots``).
3. Only a real difference queues an email (``email_outbox``), and the snapshot moves forward
   in the same transaction. A rolled-back change therefore never queues anything; a change
   that does not alter effective access (a duplicate grant, a role that adds nothing a group
   already gives) queues nothing.

Rules
-----
* One email per person per change, whatever the number of applications involved: a group
  operation produces one email for each member whose effective access changed, and none for
  the others.
* First access: when someone first holds any application (for example the default
  DijiAtWork access on their first sign-in) they get one "access available" email listing
  everything, never a separate default-application email.
* Deactivation: one "account deactivated" email, not a revocation per application.
* A quick follow-up change (within ``access_email_delay_seconds``) replaces an unsent email
  with one describing the net change; a change that is undone in time sends nothing.
* People without a snapshot (existing before this feature) get a silent baseline: we cannot
  know what they were told before, so we never guess. ``backfill`` records everyone up front.
* Failure isolation: everything here runs in a savepoint and every error is logged and
  swallowed. A notification problem can never fail or roll back the access change, and
  never blocks a sign-in.
* View-as (read-only impersonation) sessions cannot reach any mutating endpoint (``deps``),
  so they cannot cause a change and therefore cannot cause an email.

Email bodies carry application names and the kind of change only, never permission keys,
roles, client scopes or who made the change.
"""

from __future__ import annotations

import copy
import json
import logging
import re
import sys
from datetime import timedelta
from uuid import uuid4

from mail_client_py import EmailContent, EmailItem, format_subject
from sqlalchemy import event, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import PlatformRole
from app.db.base import utcnow
from app.models.audit_log import AuditLog
from app.models.email_notification import EmailOutbox, NotificationEventSetting, OutboxStatus, UserAccessSnapshot
from app.models.module import ApplicationModule
from app.models.user import User
from app.services.access_version import ACCESS_CHANGE_KEY
from app.services.authorization_service import AuthorizationService

logger = logging.getLogger(__name__)

APPLICATION_KEY = "dijione"
APPLICATION_NAME = "DijiOne"
TEMPLATE_KEY = "access_change"
# session.info flag: queue nothing for this transaction (seeding, bulk maintenance scripts).
# Snapshots still move forward so nothing is reported later either.
SUPPRESS_KEY = "suppress_access_notifications"

EVENT_WELCOME = "access.welcome"
EVENT_GRANTED = "access.granted"
EVENT_REVOKED = "access.revoked"
EVENT_UPDATED = "access.updated"
EVENT_DEACTIVATED = "account.deactivated"
EVENT_ROLE_UPDATED = "access.role_updated"
EVENT_SCOPE_UPDATED = "access.scope_updated"
EVENT_ADMINISTRATION_UPDATED = "access.administration_updated"

# Admin Center access (``users.platform_role``) is platform-owned, so it is reported as its own
# application under a platform key; every other application's name comes from the registry.
ADMIN_CENTER_KEY = "admin-center"
ADMIN_CENTER_NAME = "DijiOne Admin Center"
_ADMIN_LEVEL = {PlatformRole.PLATFORM_ADMIN.value: 1, PlatformRole.SUPER_ADMIN.value: 2}

SNAPSHOT_VERSION = 2
_ROUTE = re.compile(r"^/[A-Za-z0-9/_-]{0,120}$")  # registry routes only; never a client-supplied URL
AUDIT_KEY = "access_notification_audit"  # session.info: this transaction's audit rows, for origin

# event -> (subject purpose, description shown in Admin > Notifications)
EVENTS: dict[str, tuple[str, str]] = {
    EVENT_WELCOME: ("Access Available", "A person's DijiOne access becomes available for the first time."),
    EVENT_GRANTED: ("Access Granted", "A person gains access to one or more applications."),
    EVENT_REVOKED: ("Access Revoked", "A person loses access to one or more applications."),
    EVENT_ROLE_UPDATED: ("Role Updated", "A person's role in one application changes."),
    EVENT_SCOPE_UPDATED: ("Client Access Updated", "The clients a person can work with in one application change."),
    EVENT_ADMINISTRATION_UPDATED: (
        "Access Administration Updated",
        "A person becomes, stops being, or changes as an access administrator of one application.",
    ),
    EVENT_UPDATED: (
        "Access Updated",
        "A person's permissions change, several kinds of change happen together, or several applications change.",
    ),
    EVENT_DEACTIVATED: ("Account Deactivated", "A person's DijiOne account is deactivated."),
}

# change kind (per application) -> single-application event
_KIND_EVENT = {
    "granted": EVENT_GRANTED, "revoked": EVENT_REVOKED, "role": EVENT_ROLE_UPDATED,
    "scope": EVENT_SCOPE_UPDATED, "administration": EVENT_ADMINISTRATION_UPDATED, "updated": EVENT_UPDATED,
}

EMPTY_SNAPSHOT: dict = {"active": False, "apps": {}}


# --- snapshots and differences -----------------------------------------------------------


def _administers(authz: AuthorizationService, user: User, module_key: str, grants) -> list[str]:
    """What this person may administer in the application (delegated administration): the
    grantable roles of their saved or implied appointment, whether they may appoint other
    administrators, and any client authority. [] when they are not an access administrator."""
    if not any(g.source_type == "APPOINTMENT" for g in grants):
        return []
    saved = next((a for a in authz.appointments(user) if a.module_key == module_key), None)
    if saved is None:
        return sorted(authz.implied_appointment_roles(user, module_key))
    out = sorted(saved.grantable_roles or [])
    if saved.can_appoint_admins:
        out.append("+appoint")
    if saved.client_authority is not None:
        out += sorted(f"client:{ref}" for ref in saved.client_authority)
    return out


def _memoised_authz(session: Session) -> AuthorizationService:
    """An AuthorizationService that resolves each person's contributions and appointments once:
    a snapshot reads them for permissions, roles, administration and client scope of every
    application. Local to one snapshot, so it can never serve stale data across changes."""
    authz = AuthorizationService(session)
    contributions, appointments = {}, {}
    resolve, appointed = authz._all_contributions, authz.appointments

    def _contributions(user):
        if user.id not in contributions:
            contributions[user.id] = resolve(user)
        return contributions[user.id]

    def _appointments(user):
        if user.id not in appointments:
            appointments[user.id] = appointed(user)
        return appointments[user.id]

    authz._all_contributions = _contributions
    authz.appointments = _appointments
    return authz


def compute_snapshot(session: Session, user: User) -> dict:
    """The person's effective access now (snapshot v2).

    Per application: sorted effective permissions, the effective roles from direct, group and
    default access (``roles``), the client scope as durable client references (``clients``;
    ``None`` = all clients; only for client-scoped applications), what they may administer
    (``administers``) and whether the access comes only from default access. Plus their
    Admin Center role. Where access comes *from* (a group instead of a direct grant) is not
    part of the snapshot, so a change of source alone is never reported."""
    if not user.is_active:
        return dict(EMPTY_SNAPSHOT, apps={}, v=SNAPSHOT_VERSION, platform_role=None)
    authz = _memoised_authz(session)
    scoped = set(session.execute(
        select(ApplicationModule.key).where(ApplicationModule.supports_client_scope.is_(True))).scalars())
    apps: dict[str, dict] = {}
    for module_key, grants in sorted(authz.effective_module_roles(user).items()):
        permissions = authz.effective_permissions(user, module_key)
        if permissions:
            entry = {
                "permissions": sorted(permissions),
                "roles": sorted({g.role for g in grants if g.source_type != "APPOINTMENT"}),
                "administers": _administers(authz, user, module_key, grants),
                "default_only": all(g.source_type == "BASELINE" for g in grants),
            }
            if module_key in scoped:
                entry["clients"] = authz.effective_client_ref_scope(user, module_key)
            apps[module_key] = entry
    platform_role = user.platform_role if user.platform_role in _ADMIN_LEVEL else None
    return {"v": SNAPSHOT_VERSION, "active": True, "platform_role": platform_role, "apps": apps}


def _app_kind(old: dict | None, new: dict | None) -> str | None:
    """How one application's access changed, or None. A dimension missing from ``old`` (a v1
    snapshot written before this version) is unknown and never compared, so the upgrade to v2
    can only report what v1 would also have reported."""
    if old is None and new is None:
        return None
    if old is None:
        return "administration" if new.get("roles") == [] and new.get("administers") else "granted"
    if new is None:
        return "administration" if old.get("roles") == [] and old.get("administers") else "revoked"
    default_both = bool(old.get("default_only") and new.get("default_only"))

    def changed(key):
        return key in old and old.get(key) != new.get(key)

    perm = old["permissions"] != new["permissions"] and not default_both
    role = changed("roles") and not default_both
    scope = changed("clients") and not default_both
    admin = changed("administers")
    if not (perm or role or scope or admin):
        return None
    if admin and not (role or scope):
        return "administration"  # any permission difference comes with the appointment itself
    if role and not (scope or admin):
        return "role"
    if scope and not (role or admin):
        return "scope"
    return "updated"


def _platform_kind(before: dict, after: dict) -> str | None:
    if "platform_role" not in before:
        return None  # v1 snapshot: Admin Center access was not recorded; start silently
    old, new = _ADMIN_LEVEL.get(before.get("platform_role") or ""), _ADMIN_LEVEL.get(after.get("platform_role") or "")
    if old == new:
        return None
    if old is None:
        return "granted"
    if new is None:
        return "revoked"
    return "role"


def changes(before: dict, after: dict) -> dict[str, str]:
    """{application key: change kind} for everything that changed (Admin Center included)."""
    old, new = before.get("apps", {}), after.get("apps", {})
    out = {k: kind for k in sorted(set(old) | set(new)) if (kind := _app_kind(old.get(k), new.get(k)))}
    if after.get("active") and before.get("active", after.get("active")) and (kind := _platform_kind(before, after)):
        out[ADMIN_CENTER_KEY] = kind
    return out


def diff(before: dict, after: dict) -> tuple[list[str], list[str], list[str]]:
    """(granted, revoked, changed) application keys (administration changes count as changed)."""
    c = changes(before, after)
    return (sorted(k for k, v in c.items() if v == "granted"), sorted(k for k, v in c.items() if v == "revoked"),
            sorted(k for k, v in c.items() if v not in ("granted", "revoked")))


def classify_change(before: dict, after: dict, *, welcomed: bool) -> tuple[str | None, str | None]:
    """(event type, application key) for ``before -> after``. One application changed: that
    application's own event; welcome, deactivation and several applications: one DijiOne email."""
    if before.get("active") and not after.get("active"):
        return EVENT_DEACTIVATED, APPLICATION_KEY
    if not after.get("active"):
        return None, None
    if not welcomed and after.get("apps") and not before.get("apps"):
        return EVENT_WELCOME, APPLICATION_KEY
    c = changes(before, after)
    if not c:
        return None, None
    if len(c) == 1:
        [(app, kind)] = c.items()
        return _KIND_EVENT[kind], app
    kinds = set(c.values())
    if kinds == {"granted"}:
        return EVENT_GRANTED, APPLICATION_KEY
    if kinds == {"revoked"}:
        return EVENT_REVOKED, APPLICATION_KEY
    return EVENT_UPDATED, APPLICATION_KEY


def classify(before: dict, after: dict, *, welcomed: bool) -> str | None:
    """Which email (if any) a change from ``before`` to ``after`` deserves."""
    return classify_change(before, after, welcomed=welcomed)[0]


# --- configuration -----------------------------------------------------------------------


def event_enabled(session: Session, event_type: str) -> bool:
    """An event with no settings row is on."""
    row = session.get(NotificationEventSetting, event_type)
    return True if row is None else bool(row.enabled)


def _module_names(session: Session) -> dict[str, str]:
    """Registry display names (the only source of application names), plus the platform's own."""
    names = dict(session.execute(select(ApplicationModule.key, ApplicationModule.name)).all())
    return names | {APPLICATION_KEY: APPLICATION_NAME, ADMIN_CENTER_KEY: ADMIN_CENTER_NAME}


def _module_route(session: Session, key: str) -> str | None:
    route = session.execute(select(ApplicationModule.route).where(ApplicationModule.key == key)).scalar_one_or_none()
    return route if route and _ROUTE.match(route) else None


def _valid_address(email: str | None) -> bool:
    return bool(email) and "@" in email and not email.startswith("@") and "\n" not in email


# --- queueing ----------------------------------------------------------------------------


def _template_data(session: Session, event_type: str, app_key: str, before: dict, after: dict,
                   origin: dict | None = None) -> dict:
    names = _module_names(session)

    def named(keys):
        return [names.get(k, k) for k in keys]

    c = changes(before, after)
    data = {
        "event": event_type,
        "application_key": app_key,
        "application_name": names.get(app_key, app_key),
        "granted": named(sorted(k for k, v in c.items() if v == "granted")),
        "revoked": named(sorted(k for k, v in c.items() if v == "revoked")),
        "changed": named(sorted(k for k, v in c.items() if v in ("role", "scope", "updated"))),
        "administration": named(sorted(k for k, v in c.items() if v == "administration")),
        "changes": [{"name": names.get(k, k), "kind": v} for k, v in c.items()],
    }
    if event_type == EVENT_WELCOME:
        data["apps"] = named(sorted(after.get("apps", {})))
    if app_key not in (APPLICATION_KEY, ADMIN_CENTER_KEY) and (route := _module_route(session, app_key)):
        data["route"] = route
    if origin is not None:
        data["origin"] = origin
    return data


# --- origin (who/where a change came from; admin-facing only) -------------------------------


@event.listens_for(Session, "before_flush")
def _collect_audit_rows(session: Session, flush_context, instances) -> None:
    rows = [o for o in session.new if isinstance(o, AuditLog)]
    if rows:
        session.info.setdefault(AUDIT_KEY, []).extend(rows)


def _origin(session: Session, user: User, after: dict) -> dict:
    """Where this person's change came from, proven only by this transaction's own audit rows
    about them (never guessed from unrelated records): channel, source application, initiating
    administrator, audit references, and the groups their changed access now comes through."""
    # Only rows still in the session: a rolled-back savepoint's audit rows were expunged.
    mine = [r for r in session.info.get(AUDIT_KEY, []) if r in session and (r.subject_user_id == user.id or
            (r.entity_type == "User" and r.entity_id == user.id))]
    channels, apps, actors = set(), set(), set()
    for r in mine:
        try:
            meta = json.loads(r.event_metadata or "{}") or {}
        except (TypeError, ValueError):
            meta = {}
        if isinstance(meta, dict):
            if meta.get("channel"):
                channels.add(str(meta["channel"]))
            if meta.get("module_key"):
                apps.add(str(meta["module_key"]))
        if r.actor_id is not None:
            actors.add(r.actor_id)
    via_groups: set[str] = set()
    if any("group" in r.action for r in mine):
        authz = _memoised_authz(session)
        for grants in authz.effective_module_roles(user).values():
            via_groups |= {g.source_name for g in grants if g.source_type == "GROUP" and g.source_name}
    return {
        "channel": channels.pop() if len(channels) == 1 else ("MIXED" if channels else "UNKNOWN"),
        "source_application_key": apps.pop() if len(apps) == 1 else None,
        "actor_user_id": actors.pop() if len(actors) == 1 else None,
        "actions": sorted({r.action for r in mine}),
        "audit_ids": sorted(r.id for r in mine if r.id is not None),
        "via_groups": sorted(via_groups),
    }


def _unsent_access_email(session: Session, user_id: int) -> EmailOutbox | None:
    return session.execute(
        select(EmailOutbox)
        .where(
            EmailOutbox.recipient_user_id == user_id,
            EmailOutbox.template_key == TEMPLATE_KEY,
            EmailOutbox.status == OutboxStatus.PENDING,
            EmailOutbox.attempts == 0,
        )
        .order_by(EmailOutbox.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def queue_access_change(session: Session, user: User, before: dict, after: dict, snap: UserAccessSnapshot) -> None:
    """Queue (or fold into an unsent email) the notification for ``before -> after``."""
    settings = get_settings()
    welcomed = snap.welcomed_at is not None
    unsent = _unsent_access_email(session, user.id)
    if unsent is not None:
        # An email still unsent from before v2 starts from a v1 snapshot: complete it from the
        # stored v2 snapshot so a role/client/administration/Admin Center change is not lost.
        before = upgrade_from_snapshot(unsent.from_snapshot, before) if unsent.from_snapshot else before
        if unsent.event_type == EVENT_WELCOME:
            welcomed = False  # the welcome never went out
            snap.welcomed_at = None
        unsent.status = OutboxStatus.SUPERSEDED
        unsent.completed_at = utcnow()

    event_type, app_key = classify_change(before, after, welcomed=welcomed)
    if event_type is None or not event_enabled(session, event_type) or not _valid_address(user.email):
        return
    app_name = _module_names(session).get(app_key, app_key)
    try:
        subject = format_subject(app_name, EVENTS[event_type][0])
    except ValueError:  # a registry name that cannot appear in a subject: never lose the email
        app_key, subject = APPLICATION_KEY, format_subject(APPLICATION_NAME, EVENTS[event_type][0])
    row = EmailOutbox(
        correlation_id=str(uuid4()),
        application_key=app_key,
        event_type=event_type,
        recipient_user_id=user.id,
        recipient_email=user.email.strip(),
        subject=subject,
        template_key=TEMPLATE_KEY,
        template_data=_template_data(session, event_type, app_key, before, after, _origin(session, user, after)),
        from_snapshot=before,
        dedupe_key=f"access:{user.id}:v{snap.version}",
        status=OutboxStatus.PENDING,
        max_attempts=settings.email_max_attempts,
        not_before=utcnow() + timedelta(seconds=max(settings.access_email_delay_seconds, 0)),
    )
    session.add(row)
    if event_type == EVENT_WELCOME:
        snap.welcomed_at = utcnow()
    if unsent is not None:
        session.flush()
        unsent.superseded_by_id = row.id


def _process_user(session: Session, user_id: int, *, is_new: bool, suppress: bool) -> None:
    user = session.get(User, user_id)
    if user is None:
        return
    after = compute_snapshot(session, user)
    snap = session.get(UserAccessSnapshot, user_id)
    if snap is None:
        if not is_new:
            # Existing before this feature (or before backfill): record silently.
            session.add(UserAccessSnapshot(user_id=user_id, snapshot=after, version=0,
                                           welcomed_at=utcnow() if after["apps"] else None))
            return
        snap = UserAccessSnapshot(user_id=user_id, snapshot=dict(EMPTY_SNAPSHOT, apps={}), version=0)
        session.add(snap)
    before = snap.snapshot or dict(EMPTY_SNAPSHOT, apps={})
    if before == after:
        return
    snap.snapshot = after
    snap.version = (snap.version or 0) + 1
    if suppress:
        if after.get("apps") and snap.welcomed_at is None:
            snap.welcomed_at = utcnow()
        return
    queue_access_change(session, user, before, after, snap)


def _rebase(from_snapshot: dict, old: dict, new: dict) -> dict:
    """Carry a silent change (old -> new) into an unsent email's starting point, so folding a
    later personal change into that email never reports the silent change."""
    rebased = {k: v for k, v in from_snapshot.items() if k != "apps"} | {
        "active": from_snapshot.get("active", True), "apps": dict(from_snapshot.get("apps", {}))}
    if "platform_role" in old and "platform_role" in new and old["platform_role"] != new["platform_role"] \
            and from_snapshot.get("platform_role") == old["platform_role"]:
        rebased["platform_role"] = new["platform_role"]
    old_apps, new_apps = old.get("apps", {}), new.get("apps", {})
    for key in set(old_apps) | set(new_apps):
        if old_apps.get(key) == new_apps.get(key) or rebased["apps"].get(key) != old_apps.get(key):
            continue  # unchanged silently, or also part of the unsent personal change: keep it
        if key in new_apps:
            rebased["apps"][key] = new_apps[key]
        else:
            rebased["apps"].pop(key, None)
    return rebased


_V2_APP_KEYS = ("roles", "clients", "administers")


def upgrade_from_snapshot(from_snapshot: dict, reference: dict) -> dict:
    """Fill the v2 dimensions a v1 starting point lacks, from a v2 ``reference`` snapshot.

    Used when a change is folded into an email that is still unsent from before v2, and on
    silent realignment. For an application whose permissions are identical in both, its roles,
    clients and administration are taken from ``reference`` (v1 recorded no difference there;
    a role swap with identical permissions was invisible to v1 anyway). Applications whose
    permissions differ keep those dimensions unknown, exactly as before. Without this, a role,
    client, administration or Admin Center change folded into such an email would be lost."""
    if from_snapshot.get("v") == SNAPSHOT_VERSION or reference.get("v") != SNAPSHOT_VERSION:
        return from_snapshot
    upgraded = copy.deepcopy(from_snapshot)
    ref_apps = reference.get("apps", {})
    for key, app in upgraded.get("apps", {}).items():
        ref = ref_apps.get(key)
        if ref is not None and ref.get("permissions") == app.get("permissions"):
            for dim in _V2_APP_KEYS:
                if dim not in app and dim in ref:
                    app[dim] = copy.deepcopy(ref[dim])
    if "platform_role" not in upgraded and "platform_role" in reference:
        upgraded["platform_role"] = reference["platform_role"]
    upgraded["v"] = SNAPSHOT_VERSION
    return upgraded


def upgrade_v1_snapshots(session: Session) -> int:
    """Silently move every snapshot still in v1 form to v2 (and the starting point of their unsent
    emails). Run synchronously at startup, before the revision serves traffic, and on every
    dispatcher cycle, which picks up rows an older revision wrote during a rolling switch. Only
    v1 rows are touched; each write is optimistic. Returns rows upgraded."""
    rows = session.execute(select(UserAccessSnapshot.user_id, UserAccessSnapshot.updated_at,
                                  UserAccessSnapshot.snapshot)).all()
    upgraded = 0
    for user_id, stamp, snap in rows:
        if isinstance(snap, dict) and snap.get("v") == SNAPSHOT_VERSION:
            continue
        if realign_silently(session, user_id, expected_stamp=stamp):
            upgraded += 1
    if upgraded:
        session.commit()
    return upgraded


def realign_silently(session: Session, user_id: int, *, expected_stamp=None) -> bool:
    """Set a person's snapshot to their current access without any email or version change.

    Keeps an unsent access email intact (its content is still a true personal change) but
    rebases its starting point. With ``expected_stamp``, writes only if nobody updated the row
    since it was read (optimistic; used by the startup realignment). Returns True if changed."""
    user = session.get(User, user_id)
    snap = session.get(UserAccessSnapshot, user_id)
    if user is None or snap is None:
        return False  # no baseline yet: the next personal change (or backfill) records it
    current = compute_snapshot(session, user)
    stored = snap.snapshot or dict(EMPTY_SNAPSHOT, apps={})
    if current == stored:
        return False
    if expected_stamp is not None:
        result = session.execute(
            update(UserAccessSnapshot)
            .where(UserAccessSnapshot.user_id == user_id, UserAccessSnapshot.updated_at == expected_stamp)
            .values(snapshot=current, updated_at=utcnow())
            .execution_options(synchronize_session=False)
        )
        if not result.rowcount:
            return False
        session.expire(snap)
    else:
        snap.snapshot = current
    unsent = _unsent_access_email(session, user_id)
    if unsent is not None and unsent.from_snapshot is not None:
        unsent.from_snapshot = upgrade_from_snapshot(_rebase(unsent.from_snapshot, stored, current), current)
    return True


def is_still_accurate(session: Session, row: EmailOutbox) -> bool:
    """Whether an access email still describes the person's current access (for admin retry)."""
    if row.template_key != TEMPLATE_KEY or row.recipient_user_id is None:
        return True
    user = session.get(User, row.recipient_user_id)
    if user is None:
        return False
    newer = session.execute(
        select(EmailOutbox.id).where(
            EmailOutbox.recipient_user_id == row.recipient_user_id, EmailOutbox.template_key == TEMPLATE_KEY,
            EmailOutbox.id > row.id, EmailOutbox.status != OutboxStatus.SUPERSEDED,
        ).limit(1)
    ).first()
    if newer is not None:
        return False  # a later access email exists: this one is history
    current = compute_snapshot(session, user)
    apps, data = set(current.get("apps", {})), row.template_data or {}
    if current.get("platform_role"):
        apps.add(ADMIN_CENTER_KEY)
    names = _module_names(session)
    have = {names.get(k, k) for k in apps} | apps
    event_type = data.get("event", row.event_type)
    if event_type == EVENT_DEACTIVATED:
        return not current.get("active", True)
    if not current.get("active", True):
        return False
    if any(a not in have for a in data.get("apps", []) + data.get("granted", []) + data.get("changed", [])):
        return False
    return not any(a in have for a in data.get("revoked", []))


def process_pending(session: Session, pending: dict) -> None:
    """Email the people whose own access was changed; silently realign everyone else.

    A platform-wide change (enabling/disabling a whole application, editing the role,
    permission or default-access catalog) flags ``everyone``. Those people are *not* emailed:
    their stored snapshot is realigned silently, so the change is never reported later either.
    A person whose own assignment, group membership, delegation or account changed in the same
    transaction is processed normally."""
    new_ids = {u.id for u in pending.get("new_users", []) if u.id is not None}
    user_ids = {u for u in set(pending.get("users", set())) | new_ids if u is not None}
    suppress = bool(session.info.get(SUPPRESS_KEY))
    for user_id in sorted(user_ids):
        _process_user(session, user_id, is_new=user_id in new_ids, suppress=suppress)
    if pending.get("everyone"):
        for user_id in session.execute(select(User.id).order_by(User.id)).scalars():
            if user_id not in user_ids:
                realign_silently(session, user_id)


def _has_work(pending: dict | None) -> bool:
    return bool(pending and (pending["users"] or pending["everyone"] or pending["new_users"]))


@event.listens_for(Session, "before_commit")
def _queue_access_notifications(session: Session) -> None:
    # before_commit runs before the commit's own flush, so flush the change first (this is the
    # change's own flush: an error here surfaces exactly as it would without notifications).
    if session.new or session.dirty or session.deleted:
        session.flush()
    if not _has_work(session.info.get(ACCESS_CHANGE_KEY)):
        return
    pending = session.info.pop(ACCESS_CHANGE_KEY, None)
    if not _has_work(pending) or not get_settings().access_notifications_enabled:
        return
    try:
        with session.begin_nested():
            process_pending(session, pending)
            session.flush()
    except IntegrityError:
        # A concurrent transaction recorded the same snapshot version first. Its email stands;
        # this change will be part of the next comparison. The access change is unaffected.
        logger.warning("access notification skipped: concurrent snapshot update")
    except Exception:  # noqa: BLE001 - notifications must never break an access change or sign-in
        logger.exception("access notification could not be queued; the access change is unaffected")
    finally:
        session.info.pop(ACCESS_CHANGE_KEY, None)


@event.listens_for(Session, "after_transaction_end")
def _clear_pending(session: Session, transaction) -> None:
    if transaction.parent is None:
        session.info.pop(ACCESS_CHANGE_KEY, None)
        session.info.pop(AUDIT_KEY, None)


# --- backfill --------------------------------------------------------------------------------


def backfill_snapshots(session: Session, *, batch_size: int = 200) -> int:
    """Record a silent baseline for everyone without a snapshot. Idempotent; safe to run from
    several replicas at once (a row another replica just wrote is skipped). Returns rows added."""
    missing = list(
        session.execute(
            select(User.id).where(~User.id.in_(select(UserAccessSnapshot.user_id))).order_by(User.id)
        ).scalars()
    )
    added = 0
    for start in range(0, len(missing), batch_size):
        for user_id in missing[start:start + batch_size]:
            user = session.get(User, user_id)
            if user is None:
                continue
            after = compute_snapshot(session, user)
            try:
                with session.begin_nested():
                    session.add(UserAccessSnapshot(user_id=user_id, snapshot=after, version=0,
                                                   welcomed_at=utcnow() if after["apps"] else None))
                    session.flush()
                added += 1
            except IntegrityError:
                continue
        session.commit()
    return added


def rebaseline_snapshots(session: Session, *, batch_size: int = 200) -> int:
    """Silently bring every stored snapshot in line with current effective access.

    Access can change without an ORM flush: a release's data migration edits the role catalog,
    or a code constant (default-access permissions, implied grants) changes with the image.
    Those changes never pass through the listener, so without this the *next* unrelated change
    for a person would report them. Run at startup, after migrations: no email, version
    unchanged, unsent emails kept (their starting point rebased). Each row is written only if
    nobody updated it meanwhile (optimistic ``updated_at`` check), so a concurrent personal
    change, or another replica doing the same work, is never overwritten. Returns rows changed."""
    rows = session.execute(
        select(UserAccessSnapshot.user_id, UserAccessSnapshot.updated_at).order_by(UserAccessSnapshot.user_id)
    ).all()
    changed = 0
    for start in range(0, len(rows), batch_size):
        for user_id, stamp in rows[start:start + batch_size]:
            if realign_silently(session, user_id, expected_stamp=stamp):
                changed += 1
        session.commit()
    return changed


# --- rendering (used by the dispatcher) --------------------------------------------------------


_KIND_LABEL = {
    "granted": "Access granted", "revoked": "Access removed", "role": "Role updated",
    "scope": "Client access updated", "administration": "Access administration updated",
    "updated": "Access updated",
}


def render_access_email(row: EmailOutbox, *, portal_url: str | None) -> EmailContent:
    """The email for one access change. Application names and the kind of change only: never
    permission keys, role policies, clients or who made the change."""
    data = row.template_data or {}
    event_type = data.get("event", row.event_type)
    app_name = data.get("application_name") or APPLICATION_NAME
    single = data.get("application_key", APPLICATION_KEY) != APPLICATION_KEY
    contact = "If you think this is a mistake, please contact your DijiOne administrator."
    link = portal_url
    route = data.get("route")
    if portal_url and single and isinstance(route, str) and _ROUTE.match(route):
        link = portal_url.rstrip("/") + route  # a registry route on the DijiOne host only
    action = {"action_label": f"Open {app_name}" if single and link != portal_url else "Open DijiOne",
              "action_url": link} if link else {}
    items: list[EmailItem] = []
    if event_type == EVENT_WELCOME:
        heading = "Your DijiOne access is ready"
        paragraphs = ["Hello,", "You can now sign in to DijiOne with your Dijital Team Microsoft account. "
                      "You have access to the following applications:"]
        items = [EmailItem(name, "Available") for name in data.get("apps", [])]
    elif event_type == EVENT_DEACTIVATED:
        heading = "Your DijiOne account has been deactivated"
        paragraphs = ["Hello,", "Your DijiOne account has been deactivated, so you can no longer sign in to "
                      "DijiOne or its applications.", contact]
        action = {}
    else:
        where = app_name if single else "DijiOne"
        heading = {
            EVENT_GRANTED: f"You have been given access to {where}" if single else "You have been given access",
            EVENT_REVOKED: f"Your {where} access has been removed" if single else "Your access has been removed",
        }.get(event_type, f"Your {where} access has changed")
        paragraphs = ["Hello,", f"Your access in {where} has changed:"]
        if data.get("changes"):
            items = [EmailItem(c["name"], _KIND_LABEL.get(c.get("kind"), "Access updated")) for c in data["changes"]]
        else:  # rows queued before this version
            items = (
                [EmailItem(n, "Access granted") for n in data.get("granted", [])]
                + [EmailItem(n, "Access removed") for n in data.get("revoked", [])]
                + [EmailItem(n, "Role or permissions updated") for n in data.get("changed", [])]
            )
        if event_type == EVENT_REVOKED:
            action = {}
        if event_type != EVENT_GRANTED:
            paragraphs.append(contact)
    return EmailContent(application_name=app_name if single else APPLICATION_NAME, heading=heading,
                        paragraphs=paragraphs, items=items, **action)


if __name__ == "__main__":  # python -m app.services.access_notifications backfill
    if sys.argv[1:] != ["backfill"]:
        raise SystemExit("usage: python -m app.services.access_notifications backfill")
    from app.db.session import SessionLocal

    with SessionLocal() as _session:
        print(f"access snapshots recorded for {backfill_snapshots(_session)} users (no emails queued)")
        print(f"access snapshots realigned for {rebaseline_snapshots(_session)} users (no emails queued)")
