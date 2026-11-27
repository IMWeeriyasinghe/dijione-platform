"""One-time hire-date alignment correction for existing Production mappings.

Finds VERIFIED mappings whose ``valid_from`` date is later than the linked
BambooHR employee's hire date, and—where the correction is unambiguous and
safe—supersedes the old mapping and creates a replacement with
``valid_from = hire_date``.

Safety gates (all must pass to apply a correction):
  1. The mapping is VERIFIED with no ``valid_to`` (open/current period).
  2. The employee's hire date is known from the directory.
  3. hire_date < current valid_from (we are moving the date earlier).
  4. No other VERIFIED mapping for the same (site_id, zk_emp_code) would
     overlap if valid_from were moved earlier.
  5. The ZKBioTime code has never had a *prior* SUPERSEDED mapping whose
     valid_to >= hire_date (evidence of historical reassignment that could
     create an earlier conflict).

Corrections are skipped (not applied) when any gate fails; every skip is
recorded in the report with its reason so a human can review it.

This module never reads or writes ZKBioTime source data, BambooHR source
data, fingerprint hardware, or the Windows agent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.identity import (
    MAPPING_SUPERSEDED,
    MAPPING_VERIFIED,
    IdentityMapping,
)
from app.repositories.identity_repository import IdentityRepository
from app.services import platform_audit
from app.services.workforce_directory import DirectorySnapshot
from app.services.workforce_directory import load as _load_directory

logger = logging.getLogger("onsite-api.mapping_date_correction")

_SYSTEM_USER_ID = 0  # Sentinel for a system/batch actor. Recorded in audit rows.
_CORRECTION_NOTE = "Hire-date alignment correction: valid_from set to BambooHR hire date."


@dataclass
class CorrectionRow:
    mapping_id: int
    site_id: str
    zk_emp_code: str
    bamboohr_id: str
    current_valid_from: str
    hire_date: str
    proposed_valid_from: str
    action: str  # "CORRECTED" | "SKIPPED"
    skip_reason: str | None = None
    new_mapping_id: int | None = None


@dataclass
class CorrectionReport:
    generated_at: str
    dry_run: bool
    total_verified_open: int = 0
    already_aligned: int = 0
    hire_date_missing: int = 0
    hire_date_after_current: int = 0
    conflict_detected: int = 0
    historical_reassignment: int = 0
    corrected: int = 0
    rows: list[CorrectionRow] = field(default_factory=list)


def run(db: Session, *, dry_run: bool = True) -> CorrectionReport:
    """Main entry point. Set ``dry_run=False`` to commit corrections."""
    report = CorrectionReport(
        generated_at=datetime.now(UTC).isoformat(),
        dry_run=dry_run,
    )

    directory: DirectorySnapshot = _load_directory()
    by_bhrid = directory.by_bamboohr_id()

    stmt = (
        select(IdentityMapping)
        .where(
            IdentityMapping.status == MAPPING_VERIFIED,
            IdentityMapping.valid_to.is_(None),
        )
        .order_by(IdentityMapping.id)
    )
    open_mappings: list[IdentityMapping] = list(db.execute(stmt).scalars().all())
    report.total_verified_open = len(open_mappings)

    for m in open_mappings:
        row = _evaluate(db, m, by_bhrid)
        report.rows.append(row)
        if row.action == "CORRECTED":
            if not dry_run:
                _apply(db, m, row)
            report.corrected += 1
        elif row.skip_reason == "already_aligned":
            report.already_aligned += 1
        elif row.skip_reason == "hire_date_missing":
            report.hire_date_missing += 1
        elif row.skip_reason == "hire_date_after_current":
            report.hire_date_after_current += 1
        elif row.skip_reason == "conflict_detected":
            report.conflict_detected += 1
        elif row.skip_reason == "historical_reassignment":
            report.historical_reassignment += 1

    if not dry_run:
        db.commit()
        logger.info(
            "Mapping date correction committed: corrected=%s skipped=%s dry_run=False",
            report.corrected,
            len(report.rows) - report.corrected,
        )

    return report


# ── private helpers ────────────────────────────────────────────────────────────


def _evaluate(db: Session, m: IdentityMapping, by_bhrid: dict[str, dict]) -> CorrectionRow:
    base = CorrectionRow(
        mapping_id=m.id,
        site_id=m.site_id,
        zk_emp_code=m.zk_emp_code,
        bamboohr_id=m.bamboohr_id,
        current_valid_from=m.valid_from.isoformat(),
        hire_date="",
        proposed_valid_from="",
        action="SKIPPED",
    )

    emp = by_bhrid.get(str(m.bamboohr_id))
    if emp is None:
        base.skip_reason = "hire_date_missing"
        base.hire_date = ""
        base.proposed_valid_from = ""
        return base

    hire_raw = emp.get("hire_date")
    if not hire_raw:
        base.skip_reason = "hire_date_missing"
        base.hire_date = ""
        base.proposed_valid_from = ""
        return base

    try:
        hire: date = date.fromisoformat(str(hire_raw))
    except ValueError:
        base.skip_reason = "hire_date_missing"
        base.hire_date = str(hire_raw)
        base.proposed_valid_from = ""
        return base

    base.hire_date = hire.isoformat()
    base.proposed_valid_from = hire.isoformat()

    if hire == m.valid_from:
        base.skip_reason = "already_aligned"
        return base

    if hire > m.valid_from:
        # Hire date is AFTER current start: moving forward is unusual and
        # would narrow the coverage. Require manual review.
        base.skip_reason = "hire_date_after_current"
        return base

    # hire < valid_from: would move start date earlier — check for conflicts.
    # Gate 4: no other VERIFIED mapping for the same code that would overlap.
    conflict = _has_overlap(db, m, hire)
    if conflict:
        base.skip_reason = "conflict_detected"
        return base

    # Gate 5: no prior SUPERSEDED mapping whose valid_to >= hire (historical reassignment evidence).
    if _has_prior_owner(db, m, hire):
        base.skip_reason = "historical_reassignment"
        return base

    base.action = "CORRECTED"
    base.skip_reason = None
    return base


def _has_overlap(db: Session, mapping: IdentityMapping, proposed_from: date) -> bool:
    """True if any OTHER verified mapping for the same (site, code) covers any
    day in [proposed_from, mapping.valid_from - 1] — i.e. the new range would collide."""
    stmt = (
        select(IdentityMapping)
        .where(
            IdentityMapping.site_id == mapping.site_id,
            IdentityMapping.zk_emp_code == mapping.zk_emp_code,
            IdentityMapping.status == MAPPING_VERIFIED,
            IdentityMapping.id != mapping.id,
        )
    )
    for other in db.execute(stmt).scalars().all():
        other_end = other.valid_to
        # Does [proposed_from, mapping.valid_from-1] intersect [other.valid_from, other.valid_to or ∞]?
        new_end = mapping.valid_from  # exclusive upper bound of the extended range
        if other.valid_from < new_end and (other_end is None or other_end >= proposed_from):
            return True
    return False


def _has_prior_owner(db: Session, mapping: IdentityMapping, proposed_from: date) -> bool:
    """True if a SUPERSEDED mapping for the same code has ``valid_to >= proposed_from``
    (suggesting someone else owned this code during the target period)."""
    stmt = (
        select(IdentityMapping)
        .where(
            IdentityMapping.site_id == mapping.site_id,
            IdentityMapping.zk_emp_code == mapping.zk_emp_code,
            IdentityMapping.status == MAPPING_SUPERSEDED,
            IdentityMapping.id != mapping.id,
        )
    )
    for old in db.execute(stmt).scalars().all():
        if old.valid_to is not None and old.valid_to >= proposed_from:
            return True
    return False


def _apply(db: Session, old: IdentityMapping, row: CorrectionRow) -> None:
    """Supersede ``old`` and insert a replacement with ``valid_from = hire_date``.
    Writes one local history event and one platform audit entry."""
    from app.models.identity import SOURCE_MANUAL

    hire = date.fromisoformat(row.hire_date)
    now = datetime.now(UTC)
    repo = IdentityRepository(db)

    before = {
        "id": old.id, "site_id": old.site_id, "zk_emp_code": old.zk_emp_code,
        "bamboohr_id": old.bamboohr_id, "valid_from": old.valid_from.isoformat(),
        "valid_to": old.valid_to.isoformat() if old.valid_to else None,
        "status": old.status,
    }

    # Supersede old FIRST so the unique partial index (site_id, zk_emp_code)
    # WHERE status='VERIFIED' AND valid_to IS NULL has no conflict when the
    # replacement row is inserted.
    old.status = MAPPING_SUPERSEDED
    old.superseded_by_user_id = _SYSTEM_USER_ID
    old.superseded_at = now
    old.superseded_reason = _CORRECTION_NOTE
    db.flush()

    replacement = IdentityMapping(
        site_id=old.site_id,
        zk_emp_code=old.zk_emp_code,
        bamboohr_id=old.bamboohr_id,
        employee_number_snapshot=old.employee_number_snapshot,
        display_name_snapshot=old.display_name_snapshot,
        valid_from=hire,
        valid_to=old.valid_to,
        status=MAPPING_VERIFIED,
        evidence=_CORRECTION_NOTE,
        verified_by_user_id=_SYSTEM_USER_ID,
        verified_at=now,
        source=SOURCE_MANUAL,
    )
    db.add(replacement)
    db.flush()
    row.new_mapping_id = replacement.id
    old.superseded_by_id = replacement.id
    db.flush()

    after = {
        "id": replacement.id, "site_id": replacement.site_id,
        "zk_emp_code": replacement.zk_emp_code, "bamboohr_id": replacement.bamboohr_id,
        "valid_from": replacement.valid_from.isoformat(),
        "valid_to": replacement.valid_to.isoformat() if replacement.valid_to else None,
        "status": replacement.status,
    }
    repo.add_event(
        entity_type="MAPPING", entity_id=old.id, action="HIRE_DATE_CORRECTED",
        actor_user_id=_SYSTEM_USER_ID, previous=before, new=after, note=_CORRECTION_NOTE,
    )
    platform_audit.record(
        actor_id=_SYSTEM_USER_ID,
        entity_type="OnsiteIdentityMapping",
        entity_id=old.id,
        action="onsite.identity.mapping.hire_date_corrected",
        previous=before,
        new=after,
    )
    logger.info(
        "Mapping corrected: old_id=%s site=%s code=%s bhrid=%s %s→%s new_id=%s",
        old.id, old.site_id, old.zk_emp_code, old.bamboohr_id,
        row.current_valid_from, row.hire_date, replacement.id,
    )
