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

import logging
import sys
from datetime import timedelta
from uuid import uuid4

from mail_client_py import EmailContent, EmailItem, format_subject
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import utcnow
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

# event -> (subject purpose, description shown in Admin > Notifications)
EVENTS: dict[str, tuple[str, str]] = {
    EVENT_WELCOME: ("Access Available", "A person's DijiOne access becomes available for the first time."),
    EVENT_GRANTED: ("Access Granted", "A person gains access to one or more applications."),
    EVENT_REVOKED: ("Access Revoked", "A person loses access to one or more applications."),
    EVENT_UPDATED: (
        "Application Access Updated",
        "A person's role or permissions in an application change, or access is both added and removed.",
    ),
    EVENT_DEACTIVATED: ("Account Deactivated", "A person's DijiOne account is deactivated."),
}

EMPTY_SNAPSHOT: dict = {"active": False, "apps": {}}


# --- snapshots and differences -----------------------------------------------------------


def compute_snapshot(session: Session, user: User) -> dict:
    """The person's effective access now: active flag plus, per application, the sorted
    effective permissions and whether that access comes only from default (baseline) access.
    An application with no effective permission is not access."""
    if not user.is_active:
        return dict(EMPTY_SNAPSHOT, apps={})
    authz = AuthorizationService(session)
    apps: dict[str, dict] = {}
    for module_key, grants in sorted(authz.effective_module_roles(user).items()):
        permissions = authz.effective_permissions(user, module_key)
        if permissions:
            apps[module_key] = {
                "permissions": sorted(permissions),
                "default_only": all(g.source_type == "BASELINE" for g in grants),
            }
    return {"active": True, "apps": apps}


def diff(before: dict, after: dict) -> tuple[list[str], list[str], list[str]]:
    """(granted, revoked, changed) application keys. A permission change inside access that is
    default-only before and after (for example DijiAtWork's attendance permissions arriving
    when an employee record is matched) is part of default access, not a reportable change."""
    old, new = before.get("apps", {}), after.get("apps", {})
    granted = sorted(set(new) - set(old))
    revoked = sorted(set(old) - set(new))
    changed = sorted(
        k for k in set(old) & set(new)
        if old[k]["permissions"] != new[k]["permissions"]
        and not (old[k].get("default_only") and new[k].get("default_only"))
    )
    return granted, revoked, changed


def classify(before: dict, after: dict, *, welcomed: bool) -> str | None:
    """Which email (if any) a change from ``before`` to ``after`` deserves."""
    if before.get("active") and not after.get("active"):
        return EVENT_DEACTIVATED
    if not after.get("active"):
        return None
    if not welcomed and after.get("apps") and not before.get("apps"):
        return EVENT_WELCOME
    granted, revoked, changed = diff(before, after)
    if not (granted or revoked or changed):
        return None
    if granted and not (revoked or changed):
        return EVENT_GRANTED
    if revoked and not (granted or changed):
        return EVENT_REVOKED
    return EVENT_UPDATED


# --- configuration -----------------------------------------------------------------------


def event_enabled(session: Session, event_type: str) -> bool:
    """An event with no settings row is on."""
    row = session.get(NotificationEventSetting, event_type)
    return True if row is None else bool(row.enabled)


def _module_names(session: Session) -> dict[str, str]:
    return dict(session.execute(select(ApplicationModule.key, ApplicationModule.name)).all())


def _valid_address(email: str | None) -> bool:
    return bool(email) and "@" in email and not email.startswith("@") and "\n" not in email


# --- queueing ----------------------------------------------------------------------------


def _template_data(session: Session, event_type: str, before: dict, after: dict) -> dict:
    names = _module_names(session)

    def named(keys):
        return [names.get(k, k) for k in keys]

    granted, revoked, changed = diff(before, after)
    data = {"event": event_type, "granted": named(granted), "revoked": named(revoked), "changed": named(changed)}
    if event_type == EVENT_WELCOME:
        data["apps"] = named(sorted(after.get("apps", {})))
    return data


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
        before = unsent.from_snapshot or before
        if unsent.event_type == EVENT_WELCOME:
            welcomed = False  # the welcome never went out
            snap.welcomed_at = None
        unsent.status = OutboxStatus.SUPERSEDED
        unsent.completed_at = utcnow()

    event_type = classify(before, after, welcomed=welcomed)
    if event_type is None or not event_enabled(session, event_type) or not _valid_address(user.email):
        return
    row = EmailOutbox(
        correlation_id=str(uuid4()),
        application_key=APPLICATION_KEY,
        event_type=event_type,
        recipient_user_id=user.id,
        recipient_email=user.email.strip(),
        subject=format_subject(APPLICATION_NAME, EVENTS[event_type][0]),
        template_key=TEMPLATE_KEY,
        template_data=_template_data(session, event_type, before, after),
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


def process_pending(session: Session, pending: dict) -> None:
    new_ids = {u.id for u in pending.get("new_users", []) if u.id is not None}
    user_ids = set(pending.get("users", set())) | new_ids
    if pending.get("everyone"):
        user_ids |= set(session.execute(select(User.id)).scalars())
    suppress = bool(session.info.get(SUPPRESS_KEY))
    for user_id in sorted(u for u in user_ids if u is not None):
        _process_user(session, user_id, is_new=user_id in new_ids, suppress=suppress)


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


# --- rendering (used by the dispatcher) --------------------------------------------------------


def render_access_email(row: EmailOutbox, *, portal_url: str | None) -> EmailContent:
    data = row.template_data or {}
    event_type = data.get("event", row.event_type)
    contact = "If you think this is a mistake, please contact your DijiOne administrator."
    action = {"action_label": "Open DijiOne", "action_url": portal_url} if portal_url else {}
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
        heading = {
            EVENT_GRANTED: "You have been given access",
            EVENT_REVOKED: "Your access has been removed",
        }.get(event_type, "Your application access has changed")
        paragraphs = ["Hello,", "Your access in DijiOne has changed:"]
        items = (
            [EmailItem(n, "Access granted") for n in data.get("granted", [])]
            + [EmailItem(n, "Access removed") for n in data.get("revoked", [])]
            + [EmailItem(n, "Role or permissions updated") for n in data.get("changed", [])]
        )
        if event_type != EVENT_GRANTED:
            paragraphs.append(contact)
    return EmailContent(application_name=APPLICATION_NAME, heading=heading, paragraphs=paragraphs, items=items,
                        **action)


if __name__ == "__main__":  # python -m app.services.access_notifications backfill
    if sys.argv[1:] != ["backfill"]:
        raise SystemExit("usage: python -m app.services.access_notifications backfill")
    from app.db.session import SessionLocal

    with SessionLocal() as _session:
        print(f"access snapshots recorded for {backfill_snapshots(_session)} users (no emails queued)")
