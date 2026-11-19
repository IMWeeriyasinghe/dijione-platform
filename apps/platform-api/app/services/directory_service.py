"""Directory-backed employee provisioning and verification.

* Search the Entra directory for employees and add them to DijiOne (server-side re-read; never a
  duplicate).
* Verify an existing profile against the directory: the identity is then known before the person
  signs in (``internal_employee``), and the employee record (BambooHR) decides default employee
  access. Roles, groups and client scopes are never touched here.
* Photos and Entra group memberships, read-only, for display.

Identity (Entra) and employee record (BambooHR) are kept apart on purpose: a member account with a
company address can be a service account or a shared mailbox, so it gets no employee entitlement
until it matches an employee record (see AuthorizationService.is_eligible_employee).
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import PlatformRole
from app.integrations.directory import (
    DirectoryGroup,
    DirectoryUnavailable,
    DirectoryUser,
    Photo,
    get_directory_provider,
    is_internal_member,
)
from app.integrations.people import MATCHED, NOT_FOUND, UNKNOWN, EmployeeRecord, get_employee_record_checker
from app.models.user import User
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

LEGACY = "LEGACY"


class DirectoryError(Exception):
    """A directory operation was refused; the message says why (HTTP 400)."""


class DuplicateUserError(DirectoryError):
    """The person already has a DijiOne profile (HTTP 409); open it instead."""

    def __init__(self, existing_user_id: int) -> None:
        super().__init__("This person already has a DijiOne profile.")
        self.existing_user_id = existing_user_id


def apply_employee_record(user: User, record: EmployeeRecord, *, now: datetime | None = None) -> bool:
    """Record an employee-record check on the user. Never revokes: a LEGACY person who is not found
    stays LEGACY (and is reported for HR reconciliation), and an UNKNOWN answer keeps whatever was
    known. Returns True when the person is LEGACY and was not matched (an HR exception)."""
    now = now or datetime.now(UTC)
    if record.status == UNKNOWN:
        if user.employee_record_status is None:
            user.employee_record_status = UNKNOWN
        return False
    user.employee_record_checked_at = now
    if record.status == MATCHED:
        user.employee_record_status = MATCHED
        if record.employee_number:
            user.employee_number = record.employee_number
        return False
    if user.employee_record_status == LEGACY:
        return True
    user.employee_record_status = NOT_FOUND
    return False


def check_at_sign_in(user: User) -> None:
    """Soft employee-record check during a verified sign-in. Never blocks or fails the sign-in."""
    try:
        record = get_employee_record_checker().check(email=user.email, employee_id=user.employee_number, cached_only=True)
    except Exception:  # pragma: no cover - the checker already turns failures into UNKNOWN
        logger.warning("Employee-record check failed during sign-in")
        return
    apply_employee_record(user, record)


class _PhotoCache:
    """Small in-process cache: photos for an hour, known misses for 15 minutes."""

    def __init__(self, size: int = 500) -> None:
        self._items: OrderedDict[str, tuple[float, Photo | None]] = OrderedDict()
        self._size = size
        self._lock = threading.Lock()

    def get(self, key: str) -> tuple[bool, Photo | None]:
        with self._lock:
            item = self._items.get(key)
            if item is None or item[0] < time.monotonic():
                self._items.pop(key, None)
                return False, None
            self._items.move_to_end(key)
            return True, item[1]

    def put(self, key: str, photo: Photo | None) -> None:
        with self._lock:
            self._items[key] = (time.monotonic() + (3600 if photo else 900), photo)
            self._items.move_to_end(key)
            while len(self._items) > self._size:
                self._items.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


photo_cache = _PhotoCache()


def photo_for(object_id: str | None) -> Photo | None:
    if not object_id:
        return None
    hit, photo = photo_cache.get(object_id)
    if hit:
        return photo
    photo = get_directory_provider().photo(object_id)
    photo_cache.put(object_id, photo)
    return photo


class DirectoryService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)
        self.directory = get_directory_provider()
        self.records = get_employee_record_checker()

    # --- search ----------------------------------------------------------------------------

    def search(self, query: str) -> list[dict]:
        people = self.directory.search(query)
        if not people:
            return []
        ids = {p.object_id for p in people}
        emails = {p.email.lower() for p in people} | {p.user_principal_name.lower() for p in people}
        existing = self.db.execute(
            select(User.id, User.entra_object_id, func.lower(User.email)).where(
                or_(User.entra_object_id.in_(ids), func.lower(User.email).in_(emails))
            )
        ).all()
        by_oid = {oid: uid for uid, oid, _e in existing if oid}
        by_email = {email: uid for uid, _o, email in existing}
        out = []
        for p in people:
            record = self.records.check(email=p.email, employee_id=p.employee_id)
            out.append(
                {
                    "entra_object_id": p.object_id,
                    "full_name": p.display_name,
                    "email": p.email,
                    "user_principal_name": p.user_principal_name,
                    "job_title": p.job_title,
                    "department": p.department,
                    "employee_number": record.employee_number or p.employee_id,
                    "employee_record": record.status,
                    "existing_user_id": by_oid.get(p.object_id)
                    or by_email.get(p.email.lower())
                    or by_email.get(p.user_principal_name.lower()),
                }
            )
        return out

    # --- provisioning ----------------------------------------------------------------------

    def _existing(self, person: DirectoryUser) -> User | None:
        addresses = {person.email.lower(), person.user_principal_name.lower()}
        return self.db.execute(
            select(User).where(or_(User.entra_object_id == person.object_id, func.lower(User.email).in_(addresses)))
        ).scalars().first()

    def create_from_directory(self, *, actor: User, object_id: str) -> User:
        person = self.directory.get(object_id)  # re-read server-side: nothing from the browser is trusted
        if person is None:
            raise DirectoryError("That directory account no longer exists.")
        if not is_internal_member(person):
            raise DirectoryError("Only enabled internal member accounts can be added (not guests or disabled accounts).")
        existing = self._existing(person)
        if existing is not None:
            raise DuplicateUserError(existing.id)
        user = User(
            email=person.email.lower(), full_name=person.display_name, title=person.job_title,
            platform_role=PlatformRole.PLATFORM_USER.value, identity_provider="ENTRA", is_active=True,
        )
        self.db.add(user)
        self.db.flush()
        self.audit.log(
            actor_id=actor.id, action="user.created", entity_type="User", entity_id=user.id, subject_user_id=user.id,
            new_state={"email": user.email, "full_name": user.full_name, "platform_role": user.platform_role,
                       "is_active": True, "source": "DIRECTORY"},
        )
        self._verify(actor, user, person)
        self.db.commit()
        return user

    def onboard_for_application(self, *, actor: User, object_id: str, module_key: str) -> User:
        """An application administrator adds an employee straight from the directory.

        Narrower than ``create_from_directory``: eligibility is decided BEFORE anything is created
        (an enabled internal member account AND a matched BambooHR employee record; NOT_FOUND or
        UNKNOWN create nothing), and nothing is committed here, so the caller makes the grant in the
        same transaction. An existing profile is returned as it is, never re-verified or edited:
        verification and identity changes remain Central Admin's."""
        person = self.directory.get(object_id)  # re-read server-side: nothing from the browser is trusted
        if person is None:
            raise DirectoryError("That directory account no longer exists.")
        if not is_internal_member(person):
            raise DirectoryError("Only enabled internal member accounts can be added (not guests or disabled accounts).")
        record = self.records.check(email=person.email, employee_id=person.employee_id)
        if record.status == UNKNOWN:
            raise DirectoryError("The HR system could not be checked just now, so nobody was added. Try again later.")
        if record.status != MATCHED:
            raise DirectoryError(
                "This person is not matched to an employee record in BambooHR, so they cannot be added here. "
                "Ask Central Admin."
            )
        existing = self._existing(person)
        if existing is not None:
            # The Entra Object ID is the authoritative identity key. A profile found only by a
            # matching address is NOT the same person unless it is already linked to this object
            # id: a reused or shared address must never grant access to someone else.
            if existing.entra_object_id != person.object_id:
                raise DirectoryError(
                    "A DijiOne profile with this email address is not linked to this directory account, so "
                    "access cannot be granted here. Ask Central Admin to verify the profile."
                )
            return existing
        user = User(
            email=person.email.lower(), full_name=person.display_name, title=person.job_title,
            platform_role=PlatformRole.PLATFORM_USER.value, identity_provider="ENTRA", is_active=True,
        )
        self.db.add(user)
        self.db.flush()
        self.audit.log(
            actor_id=actor.id, action="user.created", entity_type="User", entity_id=user.id, subject_user_id=user.id,
            new_state={"email": user.email, "full_name": user.full_name, "platform_role": user.platform_role,
                       "is_active": True, "source": "APPLICATION_ONBOARDING"},
            metadata={"channel": "APPLICATION", "module_key": module_key},
        )
        self._verify(actor, user, person)  # no clash is possible: _existing found none by id or address
        return user

    def verify(self, *, actor: User, user: User) -> User:
        if user.entra_object_id:
            person = self.directory.get(user.entra_object_id)
            candidates = [person] if person is not None else []
        else:
            candidates = self.directory.find_by_email(user.email)
        if not candidates:
            self._fail(actor, user, "No directory account matches this profile.")
        if len(candidates) > 1:
            self._fail(actor, user, "More than one directory account matches this profile's email address.")
        self._verify(actor, user, candidates[0])
        self.db.commit()
        return user

    def _fail(self, actor: User, user: User, reason: str) -> None:
        self.db.rollback()
        self.audit.log(
            actor_id=actor.id, action="user.directory_verification_failed", entity_type="User", entity_id=user.id,
            subject_user_id=user.id, metadata={"reason": reason},
        )
        self.db.commit()
        raise DirectoryError(reason)

    def _verify(self, actor: User, user: User, person: DirectoryUser) -> None:
        if not is_internal_member(person):
            self._fail(actor, user, "The directory account is not an enabled internal member (guest or disabled).")
        if user.email.lower() not in {person.email.lower(), person.user_principal_name.lower()}:
            self._fail(actor, user, "The directory account's email address does not match this profile.")
        if user.entra_object_id and user.entra_object_id != person.object_id:
            self._fail(actor, user, "This profile is already bound to a different Microsoft identity.")
        clash = self.db.execute(
            select(User.id).where(User.entra_object_id == person.object_id, User.id != user.id)
        ).scalar_one_or_none()
        if clash is not None:
            self._fail(actor, user, "This Microsoft identity is already bound to another DijiOne profile.")

        now = datetime.now(UTC)
        before = {"entra_linked": bool(user.entra_object_id), "internal_employee": user.internal_employee,
                  "employee_record": user.employee_record_status}
        user.entra_object_id = person.object_id
        user.identity_provider = "ENTRA"
        user.internal_employee = True
        user.directory_verified_at = now
        if not user.title and person.job_title:
            user.title = person.job_title
        record = self.records.check(email=user.email, employee_id=person.employee_id)
        exception = apply_employee_record(user, record, now=now)
        self.db.flush()
        self.audit.log(
            actor_id=actor.id, action="user.directory_verified", entity_type="User", entity_id=user.id,
            subject_user_id=user.id, previous_state=before,
            new_state={"entra_linked": True, "internal_employee": True, "employee_record": user.employee_record_status,
                       "employee_number": user.employee_number},
            metadata={"employee_record_check": record.status, "hr_reconciliation_needed": exception},
        )

    # --- reconciliation --------------------------------------------------------------------

    def reconcile_employee_records(self, *, actor: User | None) -> dict:
        """Check every identity-verified person against BambooHR. Never revokes (see
        apply_employee_record); reports LEGACY people who were not matched for HR reconciliation.
        ``actor`` is None for the service-to-service (scheduled-style) run."""
        actor_id = actor.id if actor is not None else None
        self.records.invalidate()
        if self.records.check(email="", employee_id=None).status == UNKNOWN:
            raise DirectoryUnavailable("Employee records (BambooHR) could not be read; nothing was changed.")
        users = self.db.execute(
            select(User).where(User.internal_employee.is_(True), User.entra_object_id.is_not(None)).order_by(User.id)
        ).scalars().all()
        summary = {"checked": 0, "matched": 0, "not_found": 0, "unknown": 0, "hr_exceptions": []}
        for user in users:
            previous = user.employee_record_status
            record = self.records.check(email=user.email, employee_id=user.employee_number)
            exception = apply_employee_record(user, record)
            summary["checked"] += 1
            summary[{MATCHED: "matched", NOT_FOUND: "not_found", UNKNOWN: "unknown"}[record.status]] += 1
            if exception:
                summary["hr_exceptions"].append({"user_id": user.id, "email": user.email, "full_name": user.full_name})
            if user.employee_record_status != previous:
                self.audit.log(
                    actor_id=actor_id, action="user.employee_record_checked", entity_type="User", entity_id=user.id,
                    subject_user_id=user.id, previous_state={"employee_record": previous},
                    new_state={"employee_record": user.employee_record_status, "employee_number": user.employee_number},
                )
        self.audit.log(
            actor_id=actor_id, action="employee_records.reconciled", entity_type="Platform", entity_id=0,
            new_state={k: v for k, v in summary.items() if k != "hr_exceptions"},
            metadata={"hr_exceptions": [e["user_id"] for e in summary["hr_exceptions"]]},
        )
        self.db.commit()
        return summary

    # --- read-only display -----------------------------------------------------------------

    def entra_groups(self, user: User) -> list[DirectoryGroup]:
        if not user.entra_object_id:
            return []
        return self.directory.groups(user.entra_object_id)
