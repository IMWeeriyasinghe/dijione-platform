"""Working-day-aware delivery-date defaulting (Phase 1 §1.1).

The default delivery date for a birthday order is the birthday occurrence.
If that day falls on a supplier non-working day (weekend by default, or
whatever ``Supplier.working_days`` says), the default is shifted to the
**nearest prior working day** so DijiBirthday does not routinely schedule
deliveries a supplier cannot make. The shift is a soft flag — an
``OrderEvent`` records it — not a status change; an operator can still
override the date.

``Supplier.working_days`` is free text; this parser is deliberately
tolerant. Accepted forms (case-insensitive, any separator):
``"Mon-Fri"``, ``"Mon,Tue,Wed,Thu,Fri"``, ``"Monday Tuesday"``,
``"Mon-Sat"``. Blank / unrecognised → Monday–Friday.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

_DAY_TO_INDEX = {
    "mon": 0, "monday": 0,
    "tue": 1, "tues": 1, "tuesday": 1,
    "wed": 2, "weds": 2, "wednesday": 2,
    "thu": 3, "thur": 3, "thurs": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}
_ORDERED = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

WORKING_DAYS_DEFAULT: frozenset[int] = frozenset({0, 1, 2, 3, 4})  # Mon–Fri
CANONICAL_DEFAULT = "Mon,Tue,Wed,Thu,Fri"

_MAX_BACKTRACK_DAYS = 7


def parse_working_days(raw: str | None) -> frozenset[int]:
    """Returns the set of weekday indices (0=Mon … 6=Sun) a supplier works.
    Falls back to Mon–Fri for blank / unparseable input."""
    if not raw or not raw.strip():
        return WORKING_DAYS_DEFAULT

    text = raw.strip().lower()
    tokens = [t for t in re.split(r"[\s,;/|]+", text) if t]
    days: set[int] = set()

    for token in tokens:
        # range form, e.g. "mon-fri"
        m = re.match(r"^([a-z]+)\s*[-–—]\s*([a-z]+)$", token)
        if m and m.group(1) in _DAY_TO_INDEX and m.group(2) in _DAY_TO_INDEX:
            start_key = next(k for k in _ORDERED if _DAY_TO_INDEX[k] == _DAY_TO_INDEX[m.group(1)])
            end_key = next(k for k in _ORDERED if _DAY_TO_INDEX[k] == _DAY_TO_INDEX[m.group(2)])
            i, j = _ORDERED.index(start_key), _ORDERED.index(end_key)
            span = _ORDERED[i : j + 1] if i <= j else _ORDERED[i:] + _ORDERED[: j + 1]
            days.update(_DAY_TO_INDEX[k] for k in span)
        elif token in _DAY_TO_INDEX:
            days.add(_DAY_TO_INDEX[token])

    return frozenset(days) if days else WORKING_DAYS_DEFAULT


def canonicalise_working_days(raw: str | None) -> str:
    """Normalise arbitrary input to a stable ``"Mon,Tue,…"`` string for
    storage. Empty input canonicalises to the Mon–Fri default so the value
    is always explicit."""
    indices = parse_working_days(raw)
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    return ",".join(names[i] for i in sorted(indices)) or CANONICAL_DEFAULT


def resolve_delivery_date(occurrence: date, working_days_raw: str | None) -> tuple[date, bool]:
    """Returns ``(delivery_date, shifted)``. ``shifted`` is True when the
    birthday occurrence fell on a non-working day and the date was moved to
    the nearest prior working day."""
    working = parse_working_days(working_days_raw)
    if occurrence.weekday() in working:
        return occurrence, False

    candidate = occurrence
    for _ in range(_MAX_BACKTRACK_DAYS):
        candidate = candidate - timedelta(days=1)
        if candidate.weekday() in working:
            return candidate, True

    # Supplier "works" no recognisable day — leave the occurrence untouched
    # rather than walk back indefinitely; the exception queue / operator
    # handles a genuinely mis-configured supplier.
    return occurrence, False
