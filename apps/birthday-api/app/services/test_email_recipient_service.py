"""DijiBirthday-local non-production recipient safety allowlist —
normalization, validation, CRUD helpers, and the mail-policy integration
point (list_active_recipient_emails, consumed by
app/integrations/factory.py). See docs/platform/email-architecture.md.

Deliberately NOT in packages/mail-client-py: the shared library stays
generic (a MailPolicy given a plain list of allowed addresses) and knows
nothing about a database, a CRUD API, or Birthday's own audit model — see
that package's own docs for why."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.birthday_test_email_recipient import BirthdayTestEmailRecipient

logger = logging.getLogger(__name__)

RECIPIENT_TYPES = ("INTERNAL_TESTER", "TEST_SUPPLIER")

# Deliberately simple syntax check — good enough to catch obvious typos
# without pulling in an email-validator dependency (see
# app/schemas/test_email_recipient.py). Never a business-rules check
# (no domain allow/deny logic lives here) -- only wildcards are rejected,
# by construction, since this pattern has no "*" branch at all.
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class InvalidEmailError(ValueError):
    pass


class DuplicateRecipientError(ValueError):
    pass


def normalize_email(raw: str) -> str:
    """Trim + lowercase — the sole match/uniqueness key. Case differences
    (``Madushanka.X@`` vs ``madushanka.x@``) must be treated as the same
    recipient, per the explicit requirement."""
    return (raw or "").strip().lower()


def validate_email_syntax(raw: str) -> str:
    """Returns the trimmed (not normalized-case) address, or raises
    InvalidEmailError. No wildcard support exists at all — there is no
    code path anywhere in this module that treats ``*`` as meaningful."""
    trimmed = (raw or "").strip()
    if not trimmed or not _EMAIL_RE.match(trimmed):
        raise InvalidEmailError(f"{raw!r} is not a valid email address")
    if "*" in trimmed:
        raise InvalidEmailError("Wildcard recipients are not supported — only exact addresses.")
    return trimmed


def list_recipients(db: Session) -> list[BirthdayTestEmailRecipient]:
    return list(
        db.execute(select(BirthdayTestEmailRecipient).order_by(BirthdayTestEmailRecipient.created_at.asc()))
        .scalars()
        .all()
    )


def get_recipient_or_none(db: Session, recipient_id: int) -> BirthdayTestEmailRecipient | None:
    return db.get(BirthdayTestEmailRecipient, recipient_id)


def create_recipient(
    db: Session, *, email_address: str, display_label: str, recipient_type: str,
    is_active: bool, actor_id: int | None,
) -> BirthdayTestEmailRecipient:
    trimmed = validate_email_syntax(email_address)
    normalized = normalize_email(trimmed)
    if recipient_type not in RECIPIENT_TYPES:
        raise InvalidEmailError(f"Invalid recipient_type: {recipient_type!r}")

    existing = db.execute(
        select(BirthdayTestEmailRecipient).where(
            BirthdayTestEmailRecipient.normalized_email_address == normalized
        )
    ).scalars().first()
    if existing is not None:
        raise DuplicateRecipientError(f"{trimmed!r} is already an approved test recipient")

    recipient = BirthdayTestEmailRecipient(
        email_address=trimmed, normalized_email_address=normalized,
        display_label=display_label or trimmed, recipient_type=recipient_type,
        is_active=is_active, created_by=actor_id, updated_by=actor_id,
    )
    db.add(recipient)
    db.flush()
    return recipient


def update_recipient(
    db: Session, recipient: BirthdayTestEmailRecipient, updates: dict, *, actor_id: int | None,
) -> BirthdayTestEmailRecipient:
    if "recipient_type" in updates and updates["recipient_type"] not in RECIPIENT_TYPES:
        raise InvalidEmailError(f"Invalid recipient_type: {updates['recipient_type']!r}")
    for key in ("display_label", "recipient_type", "is_active"):
        if key in updates and updates[key] is not None:
            setattr(recipient, key, updates[key])
    recipient.updated_by = actor_id
    recipient.updated_at = datetime.now(UTC)
    db.flush()
    return recipient


def list_active_recipient_emails(db: Session) -> list[str]:
    """The mail-policy integration point (app/integrations/factory.py):
    the current, live set of normalized addresses eligible to receive real
    outbound email in a non-production environment. Queried fresh on every
    call (never cached) so activating/deactivating a recipient through the
    UI takes effect immediately, with no redeploy/restart — the explicit
    "runtime administration" requirement."""
    rows = db.execute(
        select(BirthdayTestEmailRecipient.normalized_email_address).where(
            BirthdayTestEmailRecipient.is_active.is_(True)
        )
    ).scalars().all()
    return list(rows)
