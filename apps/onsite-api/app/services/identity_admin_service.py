"""Identity Management: administrator-verified ZKBioTime ID -> BambooHR mappings.

Every write is a human decision with evidence, recorded atomically with a
local history row (``onsite_identity_events``) and, after commit, a
best-effort Platform audit event. Nothing here ever infers identity:
BambooHR Employee Number equality is shown to administrators only as a
labelled *hint* (``hint_employee_number_matches``), never pre-selected and
never applied.

Lifecycle (see the architecture review §E):
- create: a VERIFIED ownership period; ``valid_from`` is mandatory;
- close: set an end date — attribution inside the remaining period is kept;
- correct: supersede an incorrect row (optionally with a replacement) —
  only the superseded row's days lose attribution;
- reassign: hand a code to another employee from day D, keeping disjoint
  periods; a reassignment day that already has punches must be decided
  explicitly (``same_day_handling``) and is never split automatically;
- reject / withdraw: "this code is NOT this person" (optionally period-bound).
Fail closed: overlaps and rejected pairs -> 409, missing/short evidence or
unacknowledged warnings -> 422, directory unavailable -> 503.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.constants import MappingStatus
from app.models.identity import (
    MAPPING_SUPERSEDED,
    MAPPING_VERIFIED,
    REJECTION_ACTIVE,
    REJECTION_WITHDRAWN,
    SOURCE_MANUAL,
    IdentityMapping,
    IdentityRejection,
)
from app.repositories.attendance_repository import AttendanceRepository
from app.repositories.identity_repository import IdentityRepository
from app.services import platform_audit
from app.services.identity_resolution import MappingIndex
from app.services.workforce_directory import DirectorySnapshot

MIN_TEXT = 10
SAME_DAY_HANDLINGS = ("leave_unmapped", "attribute_to_new", "attribute_to_previous")


class IdentityError(Exception):
    def __init__(self, status_code: int, detail):
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class Actor:
    user_id: int
    allowed_site_ids: tuple[str, ...]


@dataclass
class MappingInput:
    site_id: str
    zk_emp_code: str
    bamboohr_id: str
    valid_from: date
    valid_to: date | None
    evidence: str
    acknowledged_warnings: tuple[str, ...] = ()


# --- serialisation --------------------------------------------------------------


def mapping_out(m: IdentityMapping, directory: DirectorySnapshot | None = None) -> dict:
    live = (directory.by_bamboohr_id().get(m.bamboohr_id) if directory and directory.available else None)
    return {
        "id": m.id, "site_id": m.site_id, "zk_emp_code": m.zk_emp_code, "bamboohr_id": m.bamboohr_id,
        "employee_name": (live or {}).get("display_name") or m.display_name_snapshot,
        "employee_number": (live or {}).get("employee_number") if live else m.employee_number_snapshot,
        "employee_in_directory": live is not None if directory and directory.available else None,
        "employee_number_snapshot": m.employee_number_snapshot, "display_name_snapshot": m.display_name_snapshot,
        "valid_from": m.valid_from.isoformat(), "valid_to": m.valid_to.isoformat() if m.valid_to else None,
        "status": m.status, "evidence": m.evidence, "source": m.source, "import_batch_id": m.import_batch_id,
        "verified_by_user_id": m.verified_by_user_id, "verified_at": _iso(m.verified_at),
        "closed_by_user_id": m.closed_by_user_id, "closed_at": _iso(m.closed_at), "closed_reason": m.closed_reason,
        "superseded_by_id": m.superseded_by_id, "superseded_by_user_id": m.superseded_by_user_id,
        "superseded_at": _iso(m.superseded_at), "superseded_reason": m.superseded_reason,
    }


def rejection_out(r: IdentityRejection) -> dict:
    return {
        "id": r.id, "site_id": r.site_id, "zk_emp_code": r.zk_emp_code, "bamboohr_id": r.bamboohr_id,
        "applies_from": r.applies_from.isoformat() if r.applies_from else None,
        "applies_to": r.applies_to.isoformat() if r.applies_to else None,
        "reason": r.reason, "status": r.status, "rejected_by_user_id": r.rejected_by_user_id,
        "rejected_at": _iso(r.rejected_at), "withdrawn_by_user_id": r.withdrawn_by_user_id,
        "withdrawn_at": _iso(r.withdrawn_at), "withdrawn_reason": r.withdrawn_reason,
    }


def _iso(v: datetime | None) -> str | None:
    return v.isoformat() if v else None


def _snapshot(m: IdentityMapping) -> dict:
    return {k: v for k, v in mapping_out(m).items() if k not in ("employee_name", "employee_number",
                                                                    "employee_in_directory")}


# --- validation helpers -----------------------------------------------------------


def _text(value: str | None, field: str) -> str:
    v = (value or "").strip()
    if len(v) < MIN_TEXT:
        raise IdentityError(422, {"error": "EVIDENCE_REQUIRED", "field": field,
                                  "message": f"{field} must be at least {MIN_TEXT} characters."})
    return v


def _site(actor: Actor, site_id: str) -> str:
    if site_id not in actor.allowed_site_ids:
        raise IdentityError(403, {"error": "SITE_NOT_ALLOWED", "message": "Site is not in your scope."})
    return site_id


def _code(code: str) -> str:
    if not code or len(code) > 20 or code != code.strip():
        raise IdentityError(422, {"error": "INVALID_CODE", "message": "ZKBioTime ID must be 1-20 characters, verbatim."})
    return code


def _directory_entry(directory: DirectorySnapshot, bamboohr_id: str) -> dict:
    if not directory.available:
        raise IdentityError(503, {"error": "DIRECTORY_UNAVAILABLE",
                                  "message": "The Workforce Directory is unavailable; try again later."})
    e = directory.by_bamboohr_id().get(str(bamboohr_id))
    if e is None:
        raise IdentityError(422, {"error": "UNKNOWN_EMPLOYEE",
                                  "message": "BHR Employee ID is not in the Workforce Directory."})
    return e


def _period(valid_from: date | None, valid_to: date | None) -> None:
    if valid_from is None:
        raise IdentityError(422, {"error": "VALID_FROM_REQUIRED",
                                  "message": "The ownership start date must be entered explicitly."})
    if valid_to is not None and valid_to < valid_from:
        raise IdentityError(422, {"error": "INVALID_PERIOD", "message": "valid_to must not be before valid_from."})


def _parse(d: str | None) -> date | None:
    return date.fromisoformat(d) if d else None


def _check_overlap(repo: IdentityRepository, actor: Actor, site_id: str, code: str, start: date, end: date | None,
                   exclude: Collection[int] = ()) -> None:
    clash = repo.overlapping_verified(allowed_site_ids=actor.allowed_site_ids, site_id=site_id, zk_emp_code=code,
                                      start=start, end=end, exclude_ids=exclude)
    if clash:
        raise IdentityError(409, {"error": "OVERLAPPING_MAPPING",
                                  "message": "This ZKBioTime ID already has a verified owner in that period.",
                                  "conflicts": [mapping_out(m) for m in clash]})


def _check_rejection(repo: IdentityRepository, actor: Actor, site_id: str, code: str, bamboohr_id: str,
                     start: date, end: date | None) -> None:
    hits = [r for r in repo.rejections(allowed_site_ids=actor.allowed_site_ids, site_id=site_id, zk_emp_code=code)
            if r.bamboohr_id == bamboohr_id and r.overlaps(start, end)]
    if hits:
        raise IdentityError(409, {"error": "REJECTED_ASSOCIATION",
                                  "message": "This association was rejected for (part of) that period; "
                                             "withdraw the rejection first if it was wrong.",
                                  "rejections": [rejection_out(r) for r in hits]})


def evidence_warnings(db: Session, actor: Actor, directory: DirectorySnapshot, site_id: str, code: str,
                      bamboohr_id: str, valid_from: date, valid_to: date | None,
                      exclude_ids: Collection[int] = ()) -> list[dict]:
    """Facts the administrator must consciously acknowledge before confirming.
    Warnings never block on their own; unacknowledged ones do."""
    out: list[dict] = []
    repo = IdentityRepository(db)
    entry = directory.by_bamboohr_id().get(str(bamboohr_id), {}) if directory.available else {}
    stats = AttendanceRepository(db).code_day_stats(allowed_site_ids=actor.allowed_site_ids, site_id=site_id,
                                                    code_windows=[(code, date.min, date.max)])
    existing = repo.mappings(allowed_site_ids=actor.allowed_site_ids, site_id=site_id, zk_emp_code=code,
                             status=MAPPING_VERIFIED)
    existing = [m for m in existing if m.id not in exclude_ids]

    def owned_elsewhere(day: date) -> bool:
        return any(m.covers(day) for m in existing)

    before = [(d, n) for _c, d, n, _l in stats if d < valid_from and not owned_elsewhere(d)]
    if before:
        out.append({"code": "PRIOR_UNMAPPED_ACTIVITY",
                    "message": f"{sum(n for _d, n in before)} earlier punches on {len(before)} day(s) "
                               f"(from {min(d for d, _ in before).isoformat()}) will remain unmapped.",
                    "events": sum(n for _d, n in before), "days": len(before),
                    "first_date": min(d for d, _ in before).isoformat()})
    if not stats:
        out.append({"code": "NO_ATTENDANCE_FOR_CODE",
                    "message": "No attendance has been recorded for this ZKBioTime ID yet."})
    hire, term = _parse(entry.get("hire_date")), _parse(entry.get("termination_date"))
    if hire and valid_from < hire:
        out.append({"code": "STARTS_BEFORE_HIRE", "message": f"Start date is before the hire date {hire.isoformat()}."})
    if term and (valid_to is None or valid_to > term):
        out.append({"code": "EXTENDS_PAST_TERMINATION",
                    "message": f"Period extends past the termination date {term.isoformat()}."})
    if entry and entry.get("employment_status") != "Active":
        out.append({"code": "EMPLOYEE_NOT_ACTIVE",
                    "message": f"Employment status is {entry.get('employment_status') or 'unknown'}."})
    others = [m for m in repo.mappings(allowed_site_ids=actor.allowed_site_ids, bamboohr_id=str(bamboohr_id),
                                       status=MAPPING_VERIFIED)
              if m.zk_emp_code != code and m.id not in exclude_ids
              and m.valid_from <= (valid_to or date.max) and valid_from <= (m.valid_to or date.max)]
    if others:
        out.append({"code": "EMPLOYEE_HAS_OTHER_CODES",
                    "message": "This employee already has other ZKBioTime ID(s) in that period: "
                               + ", ".join(sorted({m.zk_emp_code for m in others})),
                    "codes": sorted({m.zk_emp_code for m in others})})
    history = [m for m in repo.mappings(allowed_site_ids=actor.allowed_site_ids, site_id=site_id, zk_emp_code=code)
               if m.id not in exclude_ids and m.bamboohr_id != str(bamboohr_id)]
    if history:
        out.append({"code": "CODE_REUSED",
                    "message": "This ZKBioTime ID has been mapped to other employee(s) before.",
                    "mappings": [mapping_out(m) for m in history]})
    adjacent = [m for m in existing if (m.valid_to and m.valid_to + timedelta(days=1) == valid_from)
                or (valid_to and m.valid_from == valid_to + timedelta(days=1))]
    if adjacent:
        out.append({"code": "ADJACENT_MAPPING",
                    "message": "The period touches another verified period of this ZKBioTime ID.",
                    "mappings": [mapping_out(m) for m in adjacent]})
    return out


def _require_acknowledged(warnings: list[dict], acknowledged: Collection[str]) -> None:
    missing = sorted({w["code"] for w in warnings} - set(acknowledged))
    if missing:
        raise IdentityError(422, {"error": "WARNINGS_NOT_ACKNOWLEDGED", "unacknowledged": missing,
                                  "warnings": warnings})


def _audit(actor: Actor, *, entity_type: str, entity_id: int, action: str, previous: dict | None,
           new: dict | None) -> None:
    platform_audit.record(actor_id=actor.user_id, action=action, entity_type=entity_type, entity_id=entity_id,
                          previous=previous, new=new)


def _now() -> datetime:
    return datetime.now(UTC)


# --- writes ------------------------------------------------------------------------


def _insert_mapping(db: Session, actor: Actor, directory: DirectorySnapshot, data: MappingInput, *,
                    source: str = SOURCE_MANUAL, import_batch_id: str | None = None,
                    exclude_ids: Collection[int] = (), action: str = "CREATED") -> IdentityMapping:
    """Validate and add one VERIFIED row inside the caller's transaction (no commit)."""
    repo = IdentityRepository(db)
    site = _site(actor, data.site_id)
    code = _code(data.zk_emp_code)
    evidence = _text(data.evidence, "evidence")
    _period(data.valid_from, data.valid_to)
    entry = _directory_entry(directory, data.bamboohr_id)
    repo.lock_code(site, code)
    _check_overlap(repo, actor, site, code, data.valid_from, data.valid_to, exclude_ids)
    _check_rejection(repo, actor, site, code, str(data.bamboohr_id), data.valid_from, data.valid_to)
    _require_acknowledged(evidence_warnings(db, actor, directory, site, code, str(data.bamboohr_id),
                                            data.valid_from, data.valid_to, exclude_ids),
                          data.acknowledged_warnings)
    m = IdentityMapping(site_id=site, zk_emp_code=code, bamboohr_id=str(data.bamboohr_id),
                        employee_number_snapshot=entry.get("employee_number"),
                        display_name_snapshot=entry.get("display_name"),
                        valid_from=data.valid_from, valid_to=data.valid_to, status=MAPPING_VERIFIED,
                        evidence=evidence, verified_by_user_id=actor.user_id, verified_at=_now(),
                        source=source, import_batch_id=import_batch_id)
    db.add(m)
    db.flush()
    repo.add_event(entity_type="MAPPING", entity_id=m.id, action=action, actor_user_id=actor.user_id,
                   new=_snapshot(m), note=f"import {import_batch_id}" if import_batch_id else None)
    return m


def _commit(db: Session) -> None:
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


def create_mapping(db: Session, actor: Actor, directory: DirectorySnapshot, data: MappingInput) -> dict:
    try:
        m = _insert_mapping(db, actor, directory, data)
        _commit(db)
    except Exception:
        db.rollback()
        raise
    out = mapping_out(m, directory)
    _audit(actor, entity_type="OnsiteIdentityMapping", entity_id=m.id, action="onsite.identity.mapping.created",
           previous=None, new=out)
    return out


def _verified(repo: IdentityRepository, actor: Actor, mapping_id: int) -> IdentityMapping:
    m = repo.get_mapping(mapping_id, allowed_site_ids=actor.allowed_site_ids)
    if m is None:
        raise IdentityError(404, {"error": "NOT_FOUND", "message": "Mapping not found."})
    if m.status != MAPPING_VERIFIED:
        raise IdentityError(409, {"error": "NOT_VERIFIED", "message": "Only a verified mapping can be changed."})
    return m


def close_mapping(db: Session, actor: Actor, directory: DirectorySnapshot, mapping_id: int, valid_to: date,
                  reason: str) -> dict:
    """End an ownership period. Days up to ``valid_to`` stay attributed."""
    repo = IdentityRepository(db)
    try:
        reason = _text(reason, "reason")
        m = _verified(repo, actor, mapping_id)
        repo.lock_code(m.site_id, m.zk_emp_code)
        if m.valid_to is not None:
            raise IdentityError(409, {"error": "ALREADY_CLOSED",
                                      "message": "This period already has an end date; use Correct to change it."})
        if valid_to < m.valid_from:
            raise IdentityError(422, {"error": "INVALID_PERIOD", "message": "End date is before the start date."})
        before = _snapshot(m)
        m.valid_to, m.closed_by_user_id, m.closed_at, m.closed_reason = valid_to, actor.user_id, _now(), reason
        db.flush()
        repo.add_event(entity_type="MAPPING", entity_id=m.id, action="CLOSED", actor_user_id=actor.user_id,
                       previous=before, new=_snapshot(m), note=reason)
        _commit(db)
    except Exception:
        db.rollback()
        raise
    out = mapping_out(m, directory)
    _audit(actor, entity_type="OnsiteIdentityMapping", entity_id=m.id, action="onsite.identity.mapping.closed",
           previous=before, new=out)
    return out


def correct_mapping(db: Session, actor: Actor, directory: DirectorySnapshot, mapping_id: int, reason: str,
                    replacement: MappingInput | None) -> dict:
    """Supersede an incorrect row; only its own days lose attribution. An
    optional replacement for the same ZKBioTime ID is validated as a new
    mapping (excluding the superseded row) in the same transaction."""
    repo = IdentityRepository(db)
    try:
        reason = _text(reason, "reason")
        old = _verified(repo, actor, mapping_id)
        repo.lock_code(old.site_id, old.zk_emp_code)
        before = _snapshot(old)
        new = None
        if replacement is not None:
            if replacement.site_id != old.site_id or replacement.zk_emp_code != old.zk_emp_code:
                raise IdentityError(422, {"error": "REPLACEMENT_MISMATCH",
                                          "message": "A replacement must be for the same site and ZKBioTime ID."})
            new = _insert_mapping(db, actor, directory, replacement, exclude_ids=(old.id,), action="CREATED")
        old.status, old.superseded_by_user_id, old.superseded_at, old.superseded_reason = (
            MAPPING_SUPERSEDED, actor.user_id, _now(), reason)
        old.superseded_by_id = new.id if new is not None else None
        db.flush()
        repo.add_event(entity_type="MAPPING", entity_id=old.id, action="CORRECTED", actor_user_id=actor.user_id,
                       previous=before, new=_snapshot(old), note=reason)
        _commit(db)
    except Exception:
        db.rollback()
        raise
    out = {"superseded": mapping_out(old, directory), "replacement": mapping_out(new, directory) if new else None}
    _audit(actor, entity_type="OnsiteIdentityMapping", entity_id=old.id, action="onsite.identity.mapping.corrected",
           previous=before, new=out)
    return out


def reassign_code(db: Session, actor: Actor, directory: DirectorySnapshot, *, site_id: str, zk_emp_code: str,
                  effective_from: date, reason: str, new_bamboohr_id: str, new_valid_to: date | None,
                  new_evidence: str, acknowledged_warnings: Collection[str] = (),
                  same_day_handling: str | None = None) -> dict:
    """Hand a ZKBioTime ID to another employee from ``effective_from`` (D).

    Without punches on D: previous owner ends D-1, new owner starts D. With
    punches on D the caller must choose (never automatic):
    ``leave_unmapped`` (prev ends D-1, new starts D+1, day D stays unmapped),
    ``attribute_to_new`` (prev ends D-1, new starts D) or
    ``attribute_to_previous`` (prev ends D, new starts D+1)."""
    repo = IdentityRepository(db)
    try:
        site, code = _site(actor, site_id), _code(zk_emp_code)
        reason = _text(reason, "reason")
        repo.lock_code(site, code)
        current = [m for m in repo.mappings(allowed_site_ids=actor.allowed_site_ids, site_id=site, zk_emp_code=code,
                                            status=MAPPING_VERIFIED) if m.covers(effective_from)]
        if len(current) != 1:
            raise IdentityError(409, {"error": "NO_CURRENT_OWNER",
                                      "message": "No single verified owner covers that date; create a mapping instead."})
        prev = current[0]
        if prev.bamboohr_id == str(new_bamboohr_id):
            raise IdentityError(422, {"error": "SAME_EMPLOYEE", "message": "The new owner is the current owner."})
        if prev.valid_from >= effective_from:
            raise IdentityError(409, {"error": "EMPTY_PREVIOUS_PERIOD",
                                      "message": "The previous period would become empty; use Correct instead."})
        punches_on_d = sum(n for _c, _d, n, _l in AttendanceRepository(db).code_day_stats(
            allowed_site_ids=actor.allowed_site_ids, site_id=site, date_from=effective_from, date_to=effective_from,
            code_windows=[(code, effective_from, effective_from)]))
        d = effective_from
        if punches_on_d:
            if same_day_handling not in SAME_DAY_HANDLINGS:
                raise IdentityError(422, {
                    "error": "REASSIGNMENT_DAY_HAS_ACTIVITY", "events_on_day": punches_on_d,
                    "options": list(SAME_DAY_HANDLINGS),
                    "message": f"{punches_on_d} punch(es) on {d.isoformat()} cannot be split automatically; "
                               "choose same_day_handling."})
        handling = same_day_handling if punches_on_d else "attribute_to_new"
        prev_end = d if handling == "attribute_to_previous" else d - timedelta(days=1)
        new_start = d if handling == "attribute_to_new" else d + timedelta(days=1)
        if prev_end < prev.valid_from:
            raise IdentityError(409, {"error": "EMPTY_PREVIOUS_PERIOD",
                                      "message": "The previous period would become empty; use Correct instead."})
        before = _snapshot(prev)
        prev.valid_to, prev.closed_by_user_id, prev.closed_at, prev.closed_reason = (
            prev_end, actor.user_id, _now(), reason)
        db.flush()
        repo.add_event(entity_type="MAPPING", entity_id=prev.id, action="REASSIGNED", actor_user_id=actor.user_id,
                       previous=before, new=_snapshot(prev),
                       note=f"{reason} [same-day: {handling}]" if punches_on_d else reason)
        new = _insert_mapping(db, actor, directory, MappingInput(
            site_id=site, zk_emp_code=code, bamboohr_id=str(new_bamboohr_id), valid_from=new_start,
            valid_to=new_valid_to, evidence=new_evidence, acknowledged_warnings=tuple(acknowledged_warnings)),
            action="REASSIGNED")
        _commit(db)
    except Exception:
        db.rollback()
        raise
    out = {"previous": mapping_out(prev, directory), "new": mapping_out(new, directory),
           "same_day_handling": handling if punches_on_d else None,
           "unmapped_day": d.isoformat() if handling == "leave_unmapped" and punches_on_d else None}
    _audit(actor, entity_type="OnsiteIdentityMapping", entity_id=new.id, action="onsite.identity.mapping.reassigned",
           previous=before, new=out)
    return out


def reject(db: Session, actor: Actor, directory: DirectorySnapshot, *, site_id: str, zk_emp_code: str,
           bamboohr_id: str, reason: str, applies_from: date | None = None, applies_to: date | None = None) -> dict:
    repo = IdentityRepository(db)
    try:
        site, code = _site(actor, site_id), _code(zk_emp_code)
        reason = _text(reason, "reason")
        _directory_entry(directory, bamboohr_id)
        if applies_from and applies_to and applies_to < applies_from:
            raise IdentityError(422, {"error": "INVALID_PERIOD", "message": "applies_to is before applies_from."})
        repo.lock_code(site, code)
        start, end = applies_from or date.min, applies_to
        clash = [m for m in repo.overlapping_verified(allowed_site_ids=actor.allowed_site_ids, site_id=site,
                                                      zk_emp_code=code, start=start, end=end)
                 if m.bamboohr_id == str(bamboohr_id)]
        if clash:
            raise IdentityError(409, {"error": "VERIFIED_MAPPING_EXISTS",
                                      "message": "A verified mapping for this pair covers that period; correct it first.",
                                      "conflicts": [mapping_out(m) for m in clash]})
        r = IdentityRejection(site_id=site, zk_emp_code=code, bamboohr_id=str(bamboohr_id), applies_from=applies_from,
                              applies_to=applies_to, reason=reason, status=REJECTION_ACTIVE,
                              rejected_by_user_id=actor.user_id, rejected_at=_now())
        db.add(r)
        db.flush()
        repo.add_event(entity_type="REJECTION", entity_id=r.id, action="REJECTION_CREATED",
                       actor_user_id=actor.user_id, new=rejection_out(r), note=reason)
        _commit(db)
    except Exception:
        db.rollback()
        raise
    out = rejection_out(r)
    _audit(actor, entity_type="OnsiteIdentityRejection", entity_id=r.id, action="onsite.identity.rejection.created",
           previous=None, new=out)
    return out


def withdraw_rejection(db: Session, actor: Actor, rejection_id: int, reason: str) -> dict:
    repo = IdentityRepository(db)
    try:
        reason = _text(reason, "reason")
        r = repo.get_rejection(rejection_id, allowed_site_ids=actor.allowed_site_ids)
        if r is None:
            raise IdentityError(404, {"error": "NOT_FOUND", "message": "Rejection not found."})
        if r.status != REJECTION_ACTIVE:
            raise IdentityError(409, {"error": "NOT_ACTIVE", "message": "Rejection is already withdrawn."})
        before = rejection_out(r)
        r.status, r.withdrawn_by_user_id, r.withdrawn_at, r.withdrawn_reason = (
            REJECTION_WITHDRAWN, actor.user_id, _now(), reason)
        db.flush()
        repo.add_event(entity_type="REJECTION", entity_id=r.id, action="REJECTION_WITHDRAWN",
                       actor_user_id=actor.user_id, previous=before, new=rejection_out(r), note=reason)
        _commit(db)
    except Exception:
        db.rollback()
        raise
    out = rejection_out(r)
    _audit(actor, entity_type="OnsiteIdentityRejection", entity_id=r.id, action="onsite.identity.rejection.withdrawn",
           previous=before, new=out)
    return out


# --- reads ---------------------------------------------------------------------------


def _hints(directory: DirectorySnapshot, code: str, rejected: set[str]) -> list[dict]:
    """Labelled, never-applied hint: directory employees whose BambooHR
    Employee Number equals the ZKBioTime ID. Equality is NOT evidence."""
    if not directory.available:
        return []
    return [{"bamboohr_id": str(e["bamboohr_id"]), "display_name": e.get("display_name"),
             "employment_status": e.get("employment_status"), "basis": "EMPLOYEE_NUMBER_EQUALS_ID_UNVERIFIED"}
            for e in directory.by_employee_number().get(code, []) if str(e["bamboohr_id"]) not in rejected]


def _code_days(db: Session, actor: Actor, site_id: str) -> dict[str, list[tuple[date, int]]]:
    out: dict[str, list[tuple[date, int]]] = defaultdict(list)
    for code, d, n, _last in AttendanceRepository(db).code_day_stats(allowed_site_ids=actor.allowed_site_ids,
                                                                     site_id=site_id):
        out[code].append((d, n))
    return out


def unmapped_report(db: Session, actor: Actor, directory: DirectorySnapshot, *, site_id: str | None = None,
                    q: str | None = None, sort: str = "-unmapped_events", today: date | None = None) -> list[dict]:
    """Every ZKBioTime ID with attendance that is not covered by a verified
    mapping on at least one day — the outstanding mapping work."""
    index = MappingIndex.load(db, allowed_site_ids=actor.allowed_site_ids, directory=directory)
    repo = IdentityRepository(db)
    today = today or date.today()
    sites = [_site(actor, site_id)] if site_id else sorted(actor.allowed_site_ids)
    rows = []
    for site in sites:
        rejected: dict[str, set[str]] = defaultdict(set)
        rej_rows: dict[str, list[dict]] = defaultdict(list)
        for r in repo.rejections(allowed_site_ids=actor.allowed_site_ids, site_id=site):
            rejected[r.zk_emp_code].add(r.bamboohr_id)
            rej_rows[r.zk_emp_code].append(rejection_out(r))
        for code, days in _code_days(db, actor, site).items():
            unmapped = [(d, n) for d, n in days if not index.resolve(site, code, d).identified]
            if not unmapped:
                continue
            current = index.resolve(site, code, today)
            rows.append({
                "site_id": site, "zk_emp_code": code,
                "first_seen": min(d for d, _ in days).isoformat(), "last_seen": max(d for d, _ in days).isoformat(),
                "event_count": sum(n for _, n in days), "activity_days": len(days),
                "unmapped_events": sum(n for _, n in unmapped), "unmapped_days": len(unmapped),
                "first_unmapped": min(d for d, _ in unmapped).isoformat(),
                "last_unmapped": max(d for d, _ in unmapped).isoformat(),
                "mapped_today": current.identified,
                "mapping_count": len(index.periods_for_code(site, code)),
                "hint_employee_number_matches": _hints(directory, code, rejected.get(code, set())),
                "rejections": rej_rows.get(code, []),
            })
    if q:
        ql = q.strip().lower()
        rows = [r for r in rows if ql in r["zk_emp_code"].lower()]
    key = sort.lstrip("-")
    if key in {"unmapped_events", "event_count", "last_unmapped", "first_seen", "zk_emp_code", "unmapped_days"}:
        rows.sort(key=lambda r: (r[key], r["zk_emp_code"]), reverse=sort.startswith("-"))
    return rows


def code_investigation(db: Session, actor: Actor, directory: DirectorySnapshot, *, site_id: str, code: str,
                       date_from: date | None, date_to: date | None) -> dict:
    """Administrative per-day view of one ZKBioTime ID (Identity Management only)."""
    site = _site(actor, site_id)
    index = MappingIndex.load(db, allowed_site_ids=actor.allowed_site_ids, directory=directory)
    repo = IdentityRepository(db)
    days = []
    for c, d, n, last in sorted(AttendanceRepository(db).code_day_stats(
            allowed_site_ids=actor.allowed_site_ids, site_id=site, date_from=date_from, date_to=date_to,
            code_windows=[(code, date.min, date.max)]), key=lambda t: t[1]):
        r = index.resolve(site, c, d)
        days.append({"local_date": d.isoformat(), "events": n, "last_punch_utc": last.isoformat(),
                     "mapping_status": r.mapping_status.value, "bamboohr_id": r.bamboohr_id,
                     "employee_name": r.employee_name, "mapping_id": r.mapping_id})
    rejections = repo.rejections(allowed_site_ids=actor.allowed_site_ids, site_id=site, zk_emp_code=code,
                                 active_only=False)
    active_rej = {r.bamboohr_id for r in rejections if r.status == REJECTION_ACTIVE}
    return {
        "site_id": site, "zk_emp_code": code, "days": days,
        "mappings": [mapping_out(m, directory) for m in repo.mappings(
            allowed_site_ids=actor.allowed_site_ids, site_id=site, zk_emp_code=code)],
        "rejections": [rejection_out(r) for r in rejections],
        "hint_employee_number_matches": _hints(directory, code, active_rej),
        "directory_available": directory.available,
    }


def directory_search(db: Session, actor: Actor, directory: DirectorySnapshot, q: str | None) -> list[dict]:
    """Search the cached Workforce Directory. Requires a typed query: nothing is
    ever suggested or pre-selected."""
    if not directory.available:
        raise IdentityError(503, {"error": "DIRECTORY_UNAVAILABLE", "message": "The Workforce Directory is unavailable."})
    ql = (q or "").strip().lower()
    if len(ql) < 2:
        raise IdentityError(422, {"error": "QUERY_TOO_SHORT", "message": "Type at least 2 characters."})
    active_codes: dict[str, list[str]] = defaultdict(list)
    for m in IdentityRepository(db).verified_mappings(allowed_site_ids=actor.allowed_site_ids):
        active_codes[m.bamboohr_id].append(m.zk_emp_code)
    out = []
    for e in directory.entries:
        bid = str(e.get("bamboohr_id"))
        hay = [(e.get("display_name") or "").lower(), str(e.get("employee_number") or "").lower(), bid.lower()]
        if any(ql in h for h in hay):
            out.append({"bamboohr_id": bid, "display_name": e.get("display_name"),
                        "employee_number": e.get("employee_number"), "department": e.get("department"),
                        "job_title": e.get("job_title"), "employment_status": e.get("employment_status"),
                        "hire_date": e.get("hire_date"), "termination_date": e.get("termination_date"),
                        "has_photo": bool(e.get("has_photo")), "active_codes": sorted(set(active_codes.get(bid, [])))})
    out.sort(key=lambda r: ((r["display_name"] or "").lower(), r["bamboohr_id"]))
    return out


def list_mappings(db: Session, actor: Actor, directory: DirectorySnapshot, *, site_id: str | None = None,
                  status: str | None = None, bamboohr_id: str | None = None,
                  zk_emp_code: str | None = None) -> list[dict]:
    if site_id:
        _site(actor, site_id)
    return [mapping_out(m, directory) for m in IdentityRepository(db).mappings(
        allowed_site_ids=actor.allowed_site_ids, site_id=site_id, status=status, bamboohr_id=bamboohr_id,
        zk_emp_code=zk_emp_code)]


def get_mapping(db: Session, actor: Actor, directory: DirectorySnapshot, mapping_id: int) -> dict:
    repo = IdentityRepository(db)
    m = repo.get_mapping(mapping_id, allowed_site_ids=actor.allowed_site_ids)
    if m is None:
        raise IdentityError(404, {"error": "NOT_FOUND", "message": "Mapping not found."})
    return {**mapping_out(m, directory), "history": [_event_out(e) for e in repo.events(
        entity_type="MAPPING", entity_ids=[m.id])]}


def _event_out(e) -> dict:
    return {"id": e.id, "entity_type": e.entity_type, "entity_id": e.entity_id, "action": e.action,
            "actor_user_id": e.actor_user_id, "at": _iso(e.at), "previous_json": e.previous_json,
            "new_json": e.new_json, "note": e.note}


def conflicts(db: Session, actor: Actor, directory: DirectorySnapshot, *, site_id: str | None = None) -> dict:
    repo = IdentityRepository(db)
    sites = [_site(actor, site_id)] if site_id else sorted(actor.allowed_site_ids)
    verified = [m for m in repo.verified_mappings(allowed_site_ids=actor.allowed_site_ids) if m.site_id in sites]
    by_code: dict[tuple[str, str], list[IdentityMapping]] = defaultdict(list)
    by_emp: dict[str, list[IdentityMapping]] = defaultdict(list)
    for m in verified:
        by_code[(m.site_id, m.zk_emp_code)].append(m)
        by_emp[m.bamboohr_id].append(m)
    reused = [{"site_id": s, "zk_emp_code": c, "mappings": [mapping_out(m, directory) for m in ms]}
              for (s, c), ms in sorted(by_code.items()) if len({m.bamboohr_id for m in ms}) > 1]
    overlapping = []
    for (s, c), ms in by_code.items():
        ms = sorted(ms, key=lambda m: m.valid_from)
        for a, b in zip(ms, ms[1:], strict=False):
            if a.valid_to is None or a.valid_to >= b.valid_from:
                overlapping.append({"site_id": s, "zk_emp_code": c,
                                    "mappings": [mapping_out(a, directory), mapping_out(b, directory)]})
    multi = [{"bamboohr_id": bid, "codes": sorted({m.zk_emp_code for m in ms}),
              "mappings": [mapping_out(m, directory) for m in ms]}
             for bid, ms in sorted(by_emp.items()) if len({m.zk_emp_code for m in ms}) > 1]
    # Reassignment days deliberately left unmapped (previous ends D-1, next starts D+1, punches on D).
    ambiguous_days = []
    for site in sites:
        code_days = _code_days(db, actor, site)
        for (s, c), ms in by_code.items():
            if s != site:
                continue
            ms = sorted(ms, key=lambda m: m.valid_from)
            have = dict(code_days.get(c, []))
            for a, b in zip(ms, ms[1:], strict=False):
                if a.valid_to is not None and b.valid_from == a.valid_to + timedelta(days=2):
                    gap = a.valid_to + timedelta(days=1)
                    if have.get(gap):
                        ambiguous_days.append({"site_id": s, "zk_emp_code": c, "local_date": gap.isoformat(),
                                               "events": have[gap], "flag": "AMBIGUOUS_REASSIGNMENT_DAY"})
    return {
        "reused_codes": reused, "overlapping_mappings": overlapping, "employees_with_multiple_codes": multi,
        "ambiguous_reassignment_days": ambiguous_days,
        "active_rejections": [rejection_out(r) for r in repo.rejections(allowed_site_ids=actor.allowed_site_ids)
                              if r.site_id in sites],
        "recent_events": [_event_out(e) for e in repo.events(limit=100)],
    }


def readiness(db: Session, actor: Actor, directory: DirectorySnapshot, *, site_id: str, days: int = 30,
              today: date | None = None, directory_synced_at: str | None = None) -> dict:
    """Figures only — never a pass/fail. The production threshold is a
    separate human decision (architecture review §I.3)."""
    site = _site(actor, site_id)
    today = today or date.today()
    start = today - timedelta(days=days - 1)
    index = MappingIndex.load(db, allowed_site_ids=actor.allowed_site_ids, directory=directory)
    stats = AttendanceRepository(db).code_day_stats(allowed_site_ids=actor.allowed_site_ids, site_id=site,
                                                    date_from=start, date_to=today)
    total = identified = 0
    employees: set[str] = set()
    codes: set[str] = set()
    unmapped_codes: Counter = Counter()
    conflict_days = 0
    for code, d, n, _last in stats:
        total += n
        codes.add(code)
        r = index.resolve(site, code, d)
        if r.identified:
            identified += n
            employees.add(r.bamboohr_id)
        else:
            unmapped_codes[code] += n
            conflict_days += r.mapping_status == MappingStatus.MAPPING_CONFLICT
    repo = IdentityRepository(db)
    rej = {(r.zk_emp_code) for r in repo.rejections(allowed_site_ids=actor.allowed_site_ids, site_id=site)}
    top = []
    for code, n in unmapped_codes.most_common(25):
        disposition = "rejected" if code in rej else "undispositioned"
        top.append({"zk_emp_code": code, "unmapped_events": n, "disposition": disposition})
    cf = conflicts(db, actor, directory, site_id=site)
    imports = [e for e in repo.events(entity_type="IMPORT", limit=50)]
    return {
        "site_id": site, "window_days": days, "date_from": start.isoformat(), "date_to": today.isoformat(),
        "total_punches": total, "identified_punches": identified,
        "identified_punch_pct": round(100.0 * identified / total, 1) if total else None,
        "identified_employees": len(employees), "active_codes": len(codes),
        "unmapped_codes": len(unmapped_codes), "unmapped_punches": sum(unmapped_codes.values()),
        "high_volume_outstanding_codes": top,
        "unresolved_conflicts": {"conflict_days": conflict_days, "overlapping_mappings": len(cf["overlapping_mappings"]),
                                 "ambiguous_reassignment_days": len(cf["ambiguous_reassignment_days"])},
        "verified_mappings": len([m for m in repo.verified_mappings(allowed_site_ids=actor.allowed_site_ids)
                                  if m.site_id == site]),
        "mappings_without_evidence": repo.count_mappings_without_evidence(allowed_site_ids=(site,)),
        "import_batches": [_event_out(e) for e in imports],
        "directory_available": directory.available, "directory_synced_at": directory_synced_at,
        "decision": "NOT_AUTOMATIC — the production threshold is approved separately by the owner.",
    }
