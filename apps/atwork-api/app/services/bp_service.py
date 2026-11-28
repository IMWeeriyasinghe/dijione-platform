"""Business Partner role management and employee scope resolution."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.bp import AtworkBPEmployeeScope, AtworkBPGrant
from app.models.corrections import AttendanceEmployee


class BPScopeError(Exception):
    """Raised when BP scope cannot be determined safely."""


def is_bp(db: Session, platform_user_id: int) -> bool:
    row = db.execute(
        select(AtworkBPGrant).where(
            AtworkBPGrant.platform_user_id == platform_user_id,
            AtworkBPGrant.is_active.is_(True),
        )
    ).scalars().first()
    return row is not None


def get_bp_employee_scope(db: Session, bp_user_id: int) -> frozenset[int]:
    """Return the set of employee user IDs this BP is authorized to see.

    Returns an empty frozenset if no scope is defined (fail-closed).
    """
    rows = db.execute(
        select(AtworkBPEmployeeScope.employee_platform_user_id).where(
            AtworkBPEmployeeScope.bp_platform_user_id == bp_user_id,
            AtworkBPEmployeeScope.is_active.is_(True),
        )
    ).scalars().all()
    return frozenset(rows)


def resolve_employee_scope(db: Session, platform_user_id: int, has_full_management: bool) -> frozenset[int] | None:
    """Determine the authorized employee scope for a management request.

    Returns:
      None          — user has full unrestricted access (existing full manager/admin)
      frozenset     — user is a BP; this set is their authorized employee IDs
                      (may be empty if no scope assigned → fail-closed)

    Raises BPScopeError if the BP identity can't be resolved.
    """
    if has_full_management:
        return None

    if not is_bp(db, platform_user_id):
        raise BPScopeError("User has neither full Management access nor BP role")

    return get_bp_employee_scope(db, platform_user_id)


def grant_bp(db: Session, target_user_id: int, granted_by: int) -> AtworkBPGrant:
    existing = db.execute(
        select(AtworkBPGrant).where(
            AtworkBPGrant.platform_user_id == target_user_id,
            AtworkBPGrant.is_active.is_(True),
        )
    ).scalars().first()
    if existing:
        return existing

    grant = AtworkBPGrant(
        platform_user_id=target_user_id,
        granted_by=granted_by,
        granted_at=utcnow(),
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)
    return grant


def revoke_bp(db: Session, target_user_id: int, revoked_by: int) -> bool:
    grant = db.execute(
        select(AtworkBPGrant).where(
            AtworkBPGrant.platform_user_id == target_user_id,
            AtworkBPGrant.is_active.is_(True),
        )
    ).scalars().first()
    if not grant:
        return False

    grant.is_active = False
    grant.revoked_by = revoked_by
    grant.revoked_at = utcnow()

    # Deactivate all scope entries for this BP
    scope_rows = db.execute(
        select(AtworkBPEmployeeScope).where(
            AtworkBPEmployeeScope.bp_platform_user_id == target_user_id,
            AtworkBPEmployeeScope.is_active.is_(True),
        )
    ).scalars().all()
    now = utcnow()
    for row in scope_rows:
        row.is_active = False
        row.removed_by = revoked_by
        row.removed_at = now

    db.commit()
    return True


def assign_employee_to_bp(db: Session, bp_user_id: int, employee_user_id: int, assigned_by: int) -> AtworkBPEmployeeScope:
    existing = db.execute(
        select(AtworkBPEmployeeScope).where(
            AtworkBPEmployeeScope.bp_platform_user_id == bp_user_id,
            AtworkBPEmployeeScope.employee_platform_user_id == employee_user_id,
            AtworkBPEmployeeScope.is_active.is_(True),
        )
    ).scalars().first()
    if existing:
        return existing

    row = AtworkBPEmployeeScope(
        bp_platform_user_id=bp_user_id,
        employee_platform_user_id=employee_user_id,
        assigned_by=assigned_by,
        assigned_at=utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def remove_employee_from_bp(db: Session, bp_user_id: int, employee_user_id: int, removed_by: int) -> bool:
    row = db.execute(
        select(AtworkBPEmployeeScope).where(
            AtworkBPEmployeeScope.bp_platform_user_id == bp_user_id,
            AtworkBPEmployeeScope.employee_platform_user_id == employee_user_id,
            AtworkBPEmployeeScope.is_active.is_(True),
        )
    ).scalars().first()
    if not row:
        return False
    row.is_active = False
    row.removed_by = removed_by
    row.removed_at = utcnow()
    db.commit()
    return True


def list_active_bps(db: Session) -> list[dict]:
    grants = db.execute(
        select(AtworkBPGrant).where(AtworkBPGrant.is_active.is_(True))
        .order_by(AtworkBPGrant.granted_at)
    ).scalars().all()

    result = []
    for grant in grants:
        scope_count = db.execute(
            select(AtworkBPEmployeeScope).where(
                AtworkBPEmployeeScope.bp_platform_user_id == grant.platform_user_id,
                AtworkBPEmployeeScope.is_active.is_(True),
            )
        ).scalars().all()
        emp = db.get(AttendanceEmployee, grant.platform_user_id)
        result.append({
            "platform_user_id": grant.platform_user_id,
            "full_name": emp.full_name if emp else f"User #{grant.platform_user_id}",
            "work_email": emp.email if emp else None,
            "employee_count": len(scope_count),
            "granted_at": grant.granted_at,
            "granted_by": grant.granted_by,
        })
    return result
