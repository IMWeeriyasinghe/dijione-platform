"""The one DijiOne email subject convention: ``[Application Name] | Notification Purpose``.

Every application builds its subjects through ``format_subject`` so the application name is
always first and always bracketed, whichever service sends the mail. Inputs are validated
rather than silently repaired where a repair could change the meaning: a line break could
inject a header, and a bracket or pipe in the application name would break the convention
recipients and mail rules rely on.
"""

from __future__ import annotations

import re

# Graph rejects nothing below this, but mail clients truncate long subjects; keep them readable.
MAX_SUBJECT_LENGTH = 200
_WHITESPACE = re.compile(r"\s+")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class InvalidSubjectError(ValueError):
    """An application name or purpose that cannot form a convention-compliant subject."""


def _clean(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise InvalidSubjectError(f"{field} must be text")
    if "\r" in value or "\n" in value:
        raise InvalidSubjectError(f"{field} must not contain a line break")
    cleaned = _WHITESPACE.sub(" ", _CONTROL.sub(" ", value)).strip()
    if not cleaned:
        raise InvalidSubjectError(f"{field} is required")
    return cleaned


def format_subject(application_name: str, purpose: str) -> str:
    """``[Application Name] | Purpose``, e.g. ``[DijiOne] | Access Granted``."""
    app = _clean(application_name, "application name")
    if any(ch in app for ch in "[]|"):
        raise InvalidSubjectError("application name must not contain '[', ']' or '|'")
    text = _clean(purpose, "purpose")
    subject = f"[{app}] | {text}"
    if len(subject) > MAX_SUBJECT_LENGTH:
        subject = subject[: MAX_SUBJECT_LENGTH - 1].rstrip() + "…"
    return subject
