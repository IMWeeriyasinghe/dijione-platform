"""Keeps the display-name snapshot used by Management screens."""

from auth_client_py import AuthClaims
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.db.base import utcnow
from app.models.corrections import AttendanceEmployee


def remember_employee(db: Session, claims: AuthClaims) -> None:
    """Best effort: losing a race here must never block an attendance action."""
    try:
        row = db.get(AttendanceEmployee, claims.user_id)
        if row is None:
            db.add(
                AttendanceEmployee(
                    platform_user_id=claims.user_id, full_name=claims.full_name, email=claims.email, last_seen_at=utcnow()
                )
            )
        elif row.full_name != claims.full_name or row.email != claims.email:
            row.full_name = claims.full_name
            row.email = claims.email
            row.last_seen_at = utcnow()
        else:
            return
        db.commit()
    except (IntegrityError, StaleDataError):
        db.rollback()


def employee_names(db: Session, user_ids: set[int]) -> dict[int, AttendanceEmployee]:
    if not user_ids:
        return {}
    rows = db.scalars(select(AttendanceEmployee).where(AttendanceEmployee.platform_user_id.in_(user_ids)))
    return {row.platform_user_id: row for row in rows}


def display_name(names: dict[int, AttendanceEmployee], user_id: int) -> str:
    row = names.get(user_id)
    return row.full_name if row else f"User #{user_id}"
