"""Attendance exception review (v0.9) — server-enforced lifecycle.

State machine (anything else -> 409 with the allowed actions):

    (none)    --open-->     OPEN        exception type (+ optional note)
    OPEN      --submit-->   SUBMITTED   reason + explanation (>=10); optional declaration
    SUBMITTED --submit-->   SUBMITTED   (update; one history row)
    SUBMITTED --resolve-->  RESOLVED    outcome + decision note (>=10); no declaration needed
    RESOLVED  --reopen-->   REOPENED    reason (>=10)
    REOPENED  --submit-->   SUBMITTED

* Optimistic locking: every transition after ``open`` carries
  ``expected_version`` and is a conditional ``UPDATE ... WHERE version = ?``;
  a concurrent decision gets 409 and writes nothing.
* Idempotent open on the identity-day key (no duplicate case or history row).
* Append-only history: exactly one ``onsite_attendance_review_events`` row
  per transition, in the same transaction.
* Fingerprint records (``attendance_events``) and identity mappings are only
  READ here — never written.
* Observed / Declared / Estimated / Resolved stay separate. The estimate is
  ``declared departure - first recorded fingerprint`` and requires a declared
  departure at/after the LATEST fingerprint of the complete day, on the same
  site-local date (next-day declarations are rejected). Nothing is defaulted.
* Staleness is computed on read against the last snapshot and never modifies
  a case; an approved estimate is never recalculated.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.mirror import AttendanceEvent
from app.models.review import AttendanceReview, AttendanceReviewEvent
from app.repositories.attendance_repository import AttendanceRepository
from app.services import platform_audit
from app.services.attendance_summary import CODE, PERSON, VERIFIED, recorded_span, state_of
from app.services.identity_resolution import MappingIndex
from app.services.time_derivation import to_site_local

ALLOWED_ACTIONS = {
    "OPEN": ("submit",),
    "SUBMITTED": ("submit", "resolve"),
    "RESOLVED": ("reopen",),
    "REOPENED": ("submit",),
}
SOURCE_LABEL = {"TEAM_MEMBER_STATEMENT": "team member statement", "MANAGER_CONFIRMATION": "manager confirmation",
                "SECURITY_OR_VISITOR_LOG": "security or visitor log", "OTHER": "other"}
MIN_TEXT = 10
_MAX_DAY_EVENTS = 10_000


def _err(code: int, message: str, **extra) -> HTTPException:
    return HTTPException(code, {"error": message, **extra} if extra else message)


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _load(value: str | None):
    return json.loads(value) if value else None


def _hhmm(local_iso: str | None) -> str:
    return local_iso[11:16] if local_iso else "—"


# --- identity-day facts ------------------------------------------------------------


def parse_key(identity_key: str) -> tuple[str, str]:
    kind, _, value = identity_key.partition(":")
    if kind not in ("P", "C") or not value:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid identity key")
    return (PERSON if kind == "P" else CODE), value


def _identity(index: MappingIndex, site_id: str, day: date, identity_key: str) -> dict:
    """Which ZKBioTime IDs belong to the identity on ``day`` right now, and the
    mapping basis. A PERSON includes only IDs that resolve to them (conflict
    days excluded); a CODE is always just its raw ID."""
    kind, value = parse_key(identity_key)
    if kind == PERSON:
        codes, mapping_ids = set(), set()
        for p in index.periods_for_employee(value, site_id):
            if not p.covers(day):
                continue
            r = index.resolve(site_id, p.zk_emp_code, day)
            if r.identified and r.bamboohr_id == value:
                codes.add(p.zk_emp_code)
                mapping_ids.add(p.id)
        return {"kind": PERSON, "bamboohr_id": value, "zk_emp_codes": sorted(codes),
                "mapping_ids": sorted(mapping_ids), "mapping_state": VERIFIED if codes else "NOT_VERIFIED"}
    r = index.resolve(site_id, value, day)
    return {"kind": CODE, "zk_emp_code": value, "zk_emp_codes": [value],
            "mapping_ids": sorted(p.id for p in index.periods_covering(site_id, value, day)),
            "mapping_state": state_of(r)}


def day_facts(db: Session, allowed, site_id: str, tz: str | None, index: MappingIndex, day: date,
              identity_key: str) -> dict:
    """Current observed facts of one identity-day (complete day, all of the
    identity's IDs) plus the identity basis used for staleness."""
    ident = _identity(index, site_id, day, identity_key)
    events: list[AttendanceEvent] = []
    if ident["zk_emp_codes"]:
        _total, events = AttendanceRepository(db).events_page(
            allowed_site_ids=allowed, site_id=site_id, date_from=day, date_to=day,
            code_windows=[(c, day, day) for c in ident["zk_emp_codes"]], offset=0, limit=_MAX_DAY_EVENTS,
            oldest_first=True)
    n = len(events)
    first = events[0].punch_time_utc if events else None
    last = events[-1].punch_time_utc if events else None
    digest = hashlib.sha256("|".join(f"{e.event_id}@{e.punch_time_utc.isoformat()}" for e in events)
                            .encode()).hexdigest()
    facts = {
        "punch_count": n,
        "first_utc": first.isoformat() if first else None, "last_utc": last.isoformat() if last else None,
        "first_local": to_site_local(first, tz), "last_local": to_site_local(last, tz),
        "recorded_span_minutes": recorded_span(first, last, n), "events_hash": digest,
        "mapping": {"state": ident["mapping_state"], "zk_emp_codes": ident["zk_emp_codes"],
                    "mapping_ids": ident["mapping_ids"]},
    }
    punches = [{"position": i + 1, "of": n, "local_time": e.punch_time_local, "zk_emp_code": e.emp_code,
                "terminal": e.terminal_alias,
                "sequence": "SINGLE" if n == 1 else "FIRST" if i == 0 else "LAST" if i == n - 1 else "INTERMEDIATE"}
               for i, e in enumerate(events)]
    return {"identity": ident, "facts": facts, "punches": punches, "_first": first, "_last": last}


def evaluate(case: AttendanceReview, current: dict) -> dict:
    """Staleness on read. Never modifies the case."""
    snap = _load(case.facts_snapshot) or {}
    now = current["facts"]
    reasons = []
    if any(snap.get(k) != now.get(k) for k in ("punch_count", "first_utc", "last_utc", "events_hash")):
        reasons.append("FINGERPRINTS_CHANGED")
    if snap.get("mapping") != now.get("mapping"):
        reasons.append("IDENTITY_CHANGED")
    last = current["_last"]
    if case.declared_departure_utc is not None and last is not None and last > case.declared_departure_utc:
        reasons.append("ESTIMATE_BASIS_INVALID")
    return {"stale": bool(reasons), "reassess_reasons": reasons, "identity_changed": "IDENTITY_CHANGED" in reasons}


# --- declared departure ------------------------------------------------------------


def declared_departure(value: str, day: date, tz: str | None) -> tuple[str, datetime]:
    """Site-local declared departure -> (local ISO, naive UTC). Same site-local
    date only; DST gaps/folds rejected; never defaulted."""
    raw = value.strip()
    try:
        local = datetime.combine(day, time.fromisoformat(raw)) if "T" not in raw and "-" not in raw[:5] \
            else datetime.fromisoformat(raw)
    except ValueError as exc:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Declared departure must be a site-local time (HH:MM)") \
            from exc
    if local.tzinfo is not None:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY,
                   "Give the declared departure as a site-local time without a UTC offset")
    if local.date() != day:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY,
                   "Declared departure must be on the same site-local date; next-day declarations are not supported")
    zone = ZoneInfo(tz) if tz else UTC
    a, b = local.replace(tzinfo=zone, fold=0), local.replace(tzinfo=zone, fold=1)
    if a.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != local:  # spring-forward gap
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY,
                   "That local time does not exist on this date (clock change); choose another time")
    if a.utcoffset() != b.utcoffset():  # fall-back fold
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY,
                   "That local time occurs twice on this date (clock change); choose an unambiguous time")
    return a.isoformat(), a.astimezone(UTC).replace(tzinfo=None)


# --- reads --------------------------------------------------------------------------


def history(db: Session, case_id: int) -> list[dict]:
    rows = db.execute(select(AttendanceReviewEvent).where(AttendanceReviewEvent.review_id == case_id)
                      .order_by(AttendanceReviewEvent.at, AttendanceReviewEvent.id)).scalars()
    return [{"action": h.action, "from_status": h.from_status, "to_status": h.to_status, "version": h.version,
             "actor_user_id": h.actor_user_id, "actor_name": h.actor_name, "at": h.at.isoformat(),
             "note": h.note, "previous": _load(h.previous_json), "new": _load(h.new_json),
             "facts": _load(h.facts_snapshot)} for h in rows]


def serialize(case: AttendanceReview, evaluation: dict | None = None) -> dict:
    out = {
        "id": case.id, "site_id": case.site_id, "local_date": case.local_date.isoformat(),
        "identity_kind": case.identity_kind, "identity_key": case.identity_key, "bamboohr_id": case.bamboohr_id,
        "zk_emp_code": case.zk_emp_code, "identity_snapshot": _load(case.identity_snapshot),
        "exception_type": case.exception_type, "status": case.status, "version": case.version,
        "allowed_actions": list(ALLOWED_ACTIONS[case.status]),
        "justification_reason": case.justification_reason, "explanation": case.explanation,
        "declared_departure_local": case.declared_departure_local, "declaration_source": case.declaration_source,
        "evidence_reference": case.evidence_reference,
        "estimated_minutes": case.estimated_minutes, "estimate_basis": case.estimate_basis,
        "outcome": case.outcome, "decision_note": case.decision_note,
        # A resolved case is an administrative decision, never a verified duration.
        "duration_verified": False,
        "facts_snapshot": _load(case.facts_snapshot),
        "opened_by_user_id": case.opened_by_user_id, "opened_by_name": case.opened_by_name,
        "opened_at": case.opened_at.isoformat() if case.opened_at else None,
        "submitted_by_name": case.submitted_by_name,
        "submitted_at": case.submitted_at.isoformat() if case.submitted_at else None,
        "resolved_by_name": case.resolved_by_name,
        "resolved_at": case.resolved_at.isoformat() if case.resolved_at else None,
        "reopened_by_name": case.reopened_by_name,
        "reopened_at": case.reopened_at.isoformat() if case.reopened_at else None,
        "reopen_reason": case.reopen_reason,
    }
    if evaluation is not None:
        out.update(evaluation)
    return out


def summary(case: AttendanceReview, evaluation: dict) -> dict:
    """Compact review summary attached to Daily / Exceptions rows."""
    return {"id": case.id, "status": case.status, "exception_type": case.exception_type,
            "justification_reason": case.justification_reason, "outcome": case.outcome,
            "explanation": case.explanation, "declaration_source": case.declaration_source,
            "estimate_basis": case.estimate_basis, "decision_note": case.decision_note,
            "estimated_minutes": case.estimated_minutes, "declared_departure_local": case.declared_departure_local,
            "reviewer": case.resolved_by_name or case.submitted_by_name or case.opened_by_name,
            "reviewed_at": (case.resolved_at or case.submitted_at or case.opened_at).isoformat(),
            "version": case.version, "duration_verified": False, **evaluation}


def cases_in_range(db: Session, site_id: str, start: date, end: date) -> list[AttendanceReview]:
    return list(db.execute(select(AttendanceReview).where(
        AttendanceReview.site_id == site_id, AttendanceReview.local_date >= start,
        AttendanceReview.local_date <= end).order_by(AttendanceReview.local_date, AttendanceReview.id)).scalars())


def find(db: Session, site_id: str, day: date, identity_key: str) -> AttendanceReview | None:
    return db.execute(select(AttendanceReview).where(
        AttendanceReview.site_id == site_id, AttendanceReview.local_date == day,
        AttendanceReview.identity_key == identity_key)).scalar_one_or_none()


def get_in_scope(db: Session, allowed, case_id: int) -> AttendanceReview:
    case = db.get(AttendanceReview, case_id)
    if case is None or case.site_id not in allowed:
        raise _err(status.HTTP_404_NOT_FOUND, "Review case not found")
    return case


def attach(db: Session, allowed, site_id: str, tz: str | None, index: MappingIndex, rows: list[dict],
           start: date, end: date) -> None:
    """Add a ``review`` summary (or None) to each identity-day row. A verified
    row also lists CODE cases opened for one of its IDs before that ID was
    verified (``earlier_code_cases``): they stay on their original key and are
    flagged for reassessment — never moved to the person."""
    cases = {(c.local_date.isoformat(), c.identity_key): c for c in cases_in_range(db, site_id, start, end)}
    if not cases:
        for r in rows:
            r["review"] = None
        return
    for r in rows:
        key = r.get("identity_key") or (f"P:{r['bamboohr_id']}" if r.get("bamboohr_id") else f"C:{r['emp_code']}")
        case = cases.get((r["local_date"], key))
        day = date.fromisoformat(r["local_date"])
        r["review"] = summary(case, evaluate(case, day_facts(db, allowed, site_id, tz, index, day, key))) \
            if case else None
        if key.startswith("P:"):
            earlier = [cases[(r["local_date"], f"C:{c}")] for c in r.get("zk_emp_codes") or []
                       if (r["local_date"], f"C:{c}") in cases]
            if earlier:
                r["earlier_code_cases"] = [
                    summary(c, evaluate(c, day_facts(db, allowed, site_id, tz, index, day, c.identity_key)))
                    for c in earlier]


# --- writes -------------------------------------------------------------------------


def _record(db: Session, case: AttendanceReview, *, action: str, from_status: str | None, actor, previous: dict | None,
            new: dict, note: str | None, facts: dict) -> None:
    db.add(AttendanceReviewEvent(review_id=case.id, action=action, from_status=from_status, to_status=new["status"],
                                 version=new["version"], actor_user_id=actor.id, actor_name=actor.full_name,
                                 previous_json=_json(previous) if previous else None, new_json=_json(new), note=note,
                                 facts_snapshot=_json(facts)))


def _state(case: AttendanceReview) -> dict:
    return {k: getattr(case, k) for k in (
        "status", "version", "exception_type", "justification_reason", "explanation", "declared_departure_local",
        "declaration_source", "evidence_reference", "estimated_minutes", "estimate_basis", "outcome",
        "decision_note", "reopen_reason")}


def _audit(actor, action: str, case: AttendanceReview, previous: dict | None, new: dict) -> None:
    platform_audit.record(actor_id=actor.id, action=action, entity_id=case.id, previous=previous,
                          new={**new, "site_id": case.site_id, "local_date": case.local_date.isoformat(),
                               "identity_key": case.identity_key}, entity_type="OnsiteAttendanceReview")


def _require_text(value: str | None, label: str) -> str:
    text = (value or "").strip()
    if len(text) < MIN_TEXT:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{label} must be at least {MIN_TEXT} characters")
    return text


def _transition(db: Session, case: AttendanceReview, *, action: str, expected_version: int, actor, values: dict,
                facts: dict, note: str | None) -> AttendanceReview:
    if action not in ALLOWED_ACTIONS[case.status]:
        raise _err(status.HTTP_409_CONFLICT, f"'{action}' is not allowed while the case is {case.status}",
                   status=case.status, allowed_actions=list(ALLOWED_ACTIONS[case.status]))
    if case.version != expected_version:
        raise _err(status.HTTP_409_CONFLICT, "This case was changed by another administrator — reload it",
                   current_version=case.version)
    previous = _state(case)
    from_status = case.status
    now = datetime.now(UTC)
    res = db.execute(update(AttendanceReview)
                     .where(AttendanceReview.id == case.id, AttendanceReview.version == expected_version)
                     .values(**values, facts_snapshot=_json(facts), version=expected_version + 1, updated_at=now)
                     .execution_options(synchronize_session=False))
    if res.rowcount != 1:
        db.rollback()
        raise _err(status.HTTP_409_CONFLICT, "This case was changed by another administrator — reload it")
    db.expire(case)
    db.refresh(case)
    new = _state(case)
    history_action = "UPDATE" if action == "submit" and from_status == "SUBMITTED" else action.upper()
    _record(db, case, action=history_action, from_status=from_status, actor=actor, previous=previous, new=new,
            note=note, facts=facts)
    db.commit()
    _audit(actor, f"ONSITE_REVIEW_{history_action}", case, previous, new)
    return case


def open_case(db: Session, allowed, site_id: str, tz: str | None, index: MappingIndex, *, actor, day: date,
              bamboohr_id: str | None, zk_emp_code: str | None, exception_type: str,
              note: str | None) -> tuple[AttendanceReview, bool]:
    if bool(bamboohr_id) == bool(zk_emp_code):
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Give exactly one of bamboohr_id or zk_emp_code")
    if zk_emp_code:
        if state_of(index.resolve(site_id, zk_emp_code, day)) == VERIFIED:
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY,
                       "This ZKBioTime ID is verified for that day — open the case for the team member instead")
        key = f"C:{zk_emp_code}"
    else:
        key = f"P:{bamboohr_id}"
    existing = find(db, site_id, day, key)
    if existing is not None:
        return existing, False
    current = day_facts(db, allowed, site_id, tz, index, day, key)
    if current["facts"]["punch_count"] == 0:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "No recorded fingerprints for this identity on this day")
    kind, _value = parse_key(key)
    case = AttendanceReview(
        site_id=site_id, local_date=day, identity_kind=kind, identity_key=key,
        bamboohr_id=bamboohr_id if kind == PERSON else None, zk_emp_code=zk_emp_code if kind == CODE else None,
        identity_snapshot=_json(current["identity"]), exception_type=exception_type, status="OPEN", version=1,
        facts_snapshot=_json(current["facts"]), opened_by_user_id=actor.id, opened_by_name=actor.full_name)
    db.add(case)
    try:
        db.flush()
        new = _state(case)
        _record(db, case, action="OPEN", from_status=None, actor=actor, previous=None, new=new,
                note=(note or "").strip() or None, facts=current["facts"])
        db.commit()
    except IntegrityError:  # a concurrent open of the same identity-day won the race
        db.rollback()
        winner = find(db, site_id, day, key)
        if winner is None:
            raise
        return winner, False
    _audit(actor, "ONSITE_REVIEW_OPEN", case, None, new)
    return case, True


def submit(db: Session, allowed, case: AttendanceReview, tz: str | None, index: MappingIndex, *, actor,
           expected_version: int, reason: str, explanation: str, declared_departure_local: str | None,
           declaration_source: str | None, evidence_reference: str | None) -> AttendanceReview:
    text = _require_text(explanation, "Explanation")
    current = day_facts(db, allowed, case.site_id, tz, index, case.local_date, case.identity_key)
    values = {"justification_reason": reason, "explanation": text,
              "evidence_reference": (evidence_reference or "").strip() or None,
              "declared_departure_local": None, "declared_departure_utc": None, "declaration_source": None,
              "estimated_minutes": None, "estimate_basis": None,
              # Resubmission supersedes any earlier decision (kept in the history).
              "outcome": None, "decision_note": None, "resolved_by_user_id": None, "resolved_by_name": None,
              "resolved_at": None,
              "status": "SUBMITTED", "submitted_by_user_id": actor.id, "submitted_by_name": actor.full_name,
              "submitted_at": datetime.now(UTC)}
    if declared_departure_local and declared_departure_local.strip():
        if not declaration_source:
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "A declared departure requires a declaration source")
        first, last = current["_first"], current["_last"]
        if first is None:
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY,
                       "No recorded fingerprints for this identity on this day — a departure cannot be declared")
        local_iso, utc = declared_departure(declared_departure_local, case.local_date, tz)
        if utc < last:
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY,
                       f"Declared departure must not be earlier than the latest recorded fingerprint "
                       f"({_hhmm(current['facts']['last_local'])})")
        if utc <= first:
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY,
                       f"Declared departure must be later than the first recorded fingerprint "
                       f"({_hhmm(current['facts']['first_local'])})")
        minutes = int((utc - first).total_seconds() // 60)
        values.update({
            "declared_departure_local": local_iso, "declared_departure_utc": utc,
            "declaration_source": declaration_source, "estimated_minutes": minutes,
            "estimate_basis": (f"First recorded fingerprint {_hhmm(current['facts']['first_local'])} → declared "
                               f"departure {local_iso[11:16]} ({tz or 'UTC'}); source: "
                               f"{SOURCE_LABEL.get(declaration_source, declaration_source)}; recorded by "
                               f"{actor.full_name}. Reviewed declaration — not a confirmed duration."),
        })
    return _transition(db, case, action="submit", expected_version=expected_version, actor=actor, values=values,
                       facts=current["facts"], note=None)


def resolve(db: Session, allowed, case: AttendanceReview, tz: str | None, index: MappingIndex, *, actor,
            expected_version: int, outcome: str, decision_note: str) -> AttendanceReview:
    note = _require_text(decision_note, "Decision note")
    current = day_facts(db, allowed, case.site_id, tz, index, case.local_date, case.identity_key)
    if case.status == "SUBMITTED" and evaluate(case, current)["stale"]:
        raise _err(status.HTTP_409_CONFLICT,
                   "Recorded fingerprints or the identity mapping changed since the justification was submitted — "
                   "review the current facts and resubmit first", status=case.status, allowed_actions=["submit"])
    values = {"status": "RESOLVED", "outcome": outcome, "decision_note": note, "resolved_by_user_id": actor.id,
              "resolved_by_name": actor.full_name, "resolved_at": datetime.now(UTC)}
    return _transition(db, case, action="resolve", expected_version=expected_version, actor=actor, values=values,
                       facts=current["facts"], note=note)


def reopen(db: Session, allowed, case: AttendanceReview, tz: str | None, index: MappingIndex, *, actor,
           expected_version: int, reason: str) -> AttendanceReview:
    text = _require_text(reason, "Reopen reason")
    current = day_facts(db, allowed, case.site_id, tz, index, case.local_date, case.identity_key)
    values = {"status": "REOPENED", "reopened_by_user_id": actor.id, "reopened_by_name": actor.full_name,
              "reopened_at": datetime.now(UTC), "reopen_reason": text}
    # Keep the snapshot the decision was made on: staleness stays visible while reopened.
    return _transition(db, case, action="reopen", expected_version=expected_version, actor=actor, values=values,
                       facts=_load(case.facts_snapshot) or current["facts"], note=text)
