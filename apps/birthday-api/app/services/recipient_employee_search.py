"""Employee lookup for the Email Safety allowlist (non-production only).

Searches the People / Workforce domain (people-api, BambooHR active employees), the employee source
birthday-api already consumes. Microsoft Graph is not used: birthday-api's own Graph identity is a
mail-only app registration with no directory permission, and adding one is out of scope.

Selecting an employee only fills in the recipient's address and label. The allowlist stays a plain list
of email addresses: an entry never creates or implies a DijiOne identity or any application access, and
an employee who later leaves never widens who may receive mail (``employee_matches`` reports them so
an administrator can deactivate the entry).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.factory import get_employee_source
from app.models.birthday_test_email_recipient import BirthdayTestEmailRecipient
from app.services.test_email_recipient_service import normalize_email

SEARCH_LIMIT = 15
ACTIVE, NOT_ACTIVE = "ACTIVE_EMPLOYEE", "NOT_AN_ACTIVE_EMPLOYEE"


def _active_by_email() -> dict[str, object]:
    """Active employees keyed by normalized work email; duplicates (the same person or address twice)
    collapse to one entry. Raises EmployeeSourceFetchError when people-api cannot be read."""
    out: dict[str, object] = {}
    for e in get_employee_source().list_active_employees():
        email = (e.work_email or "").strip().lower()
        if email and email not in out:
            out[email] = e
    return out


def search_employees(db: Session, query: str) -> list[dict]:
    q = (query or "").strip().lower()
    if len(q) < 2:
        raise ValueError("Type at least 2 characters.")
    existing = set(db.execute(select(BirthdayTestEmailRecipient.normalized_email_address)).scalars())
    hits = []
    for email, e in sorted(_active_by_email().items(), key=lambda kv: kv[1].display_name.lower()):
        if q in e.display_name.lower() or q in email:
            hits.append({
                "full_name": e.display_name, "email_address": email, "department": e.department or None,
                "already_recipient": email in existing,
            })
            if len(hits) >= SEARCH_LIMIT:
                break
    return hits


def employee_matches(db: Session) -> dict[str, str]:
    """For each allowlisted address: ACTIVE_EMPLOYEE or NOT_AN_ACTIVE_EMPLOYEE (a manual entry, or an
    employee who has left). Informational only; nothing is changed automatically."""
    active = _active_by_email()
    rows = db.execute(select(BirthdayTestEmailRecipient.normalized_email_address)).scalars()
    return {email: (ACTIVE if email in active else NOT_ACTIVE) for email in rows}


__all__ = ["search_employees", "employee_matches", "normalize_email"]
