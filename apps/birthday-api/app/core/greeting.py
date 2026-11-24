"""Default birthday greeting for a cake order.

The salutation uses the first name taken from the employee's WORK EMAIL
(the business found BambooHR first/last/preferred names inconsistent), with
the display name as a safe fallback. This rule is only used to generate the
greeting text; the employee's stored name is never changed.
"""

from __future__ import annotations

import re

GREETING_MAX_LENGTH = 2000

_SEPARATORS = re.compile(r"[._\-+]")
_LETTERS_ONLY = re.compile(r"[^A-Za-zÀ-ɏ]")

DEFAULT_GREETING_TEMPLATE = (
    "Happy Birthday {first_name}!\n"
    "\n"
    "On behalf of everyone at Dijital Team, we wanted to wish you a wonderful day "
    "and best wishes for the year ahead!\n"
    "\n"
    "All the very best!!\n"
    "\n"
    "- Peter Ward"
)
_NO_NAME_GREETING_OPENING = "Happy Birthday!"


def _title(word: str) -> str:
    return word[:1].upper() + word[1:].lower()


def _clean_segment(segment: str) -> str:
    return _LETTERS_ONLY.sub("", segment)


def first_name_from_email(email: str | None) -> str | None:
    """`nirmani.dahanayaka@x` -> `Nirmani`; `IMAZ_HAMEED@x` -> `Imaz`.
    None when the local part has no sensible alphabetic first segment
    (a single letter is treated as an initial, not a name)."""
    local = (email or "").strip().split("@", 1)[0]
    if not local:
        return None
    segment = _clean_segment(_SEPARATORS.split(local, 1)[0])
    if len(segment) < 2:
        return None
    return _title(segment)


def first_name_from_display_name(display_name: str | None) -> str | None:
    for token in (display_name or "").split():
        word = _clean_segment(token)
        if len(word) >= 2:
            return _title(word)
    return None


def greeting_first_name(email: str | None, display_name: str | None) -> str | None:
    return first_name_from_email(email) or first_name_from_display_name(display_name)


def default_greeting(first_name: str | None) -> str:
    if not first_name:
        return DEFAULT_GREETING_TEMPLATE.replace("Happy Birthday {first_name}!", _NO_NAME_GREETING_OPENING)
    return DEFAULT_GREETING_TEMPLATE.format(first_name=first_name)


def default_greeting_for(email: str | None, display_name: str | None) -> str:
    return default_greeting(greeting_first_name(email, display_name))


def normalise_greeting(text: str) -> str:
    """Stored form of an edited greeting: LF line breaks, no trailing
    whitespace on lines, no leading/trailing blank lines. Interior
    paragraph breaks are preserved exactly."""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(lines).strip("\n")
