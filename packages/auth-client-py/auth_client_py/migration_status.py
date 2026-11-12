"""Alembic migration drift diagnostic for ``/health/deep``.

Given a service's alembic *script directory* (the folder containing
``env.py`` and ``versions/``) and the revision currently recorded in its
``alembic_version`` table, report whether the schema is at head. ``alembic``
is imported lazily so this module adds no import cost to a service that
doesn't own a database.
"""

from __future__ import annotations


def alembic_head_status(script_location: str, current_rev: str | None) -> dict:
    """Return ``{"current", "head", "up_to_date"}``.

    ``up_to_date`` is ``True`` only when ``current_rev`` is one of the
    revision graph's heads, ``False`` when it is behind, and ``None`` when
    the head could not be determined (bad path, unreadable scripts).
    """
    try:
        from alembic.script import ScriptDirectory

        heads = list(ScriptDirectory(script_location).get_heads())
    except Exception as exc:  # noqa: BLE001 - a diagnostic must never crash the probe
        return {
            "current": current_rev or "none",
            "head": "unknown",
            "up_to_date": None,
            "error": exc.__class__.__name__,
        }

    if not heads:
        head_repr = "none"
    elif len(heads) == 1:
        head_repr = heads[0]
    else:
        head_repr = ",".join(sorted(heads))

    up_to_date = bool(current_rev) and current_rev in heads
    return {"current": current_rev or "none", "head": head_repr, "up_to_date": up_to_date}
