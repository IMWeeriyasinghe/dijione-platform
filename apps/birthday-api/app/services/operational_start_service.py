"""Operational go-live boundary and the one-time clean start (DIJI Birthday V1).

first eligible birthday = operational_start_date + supplier_lead_time_days

* The daily scan never creates an order for an occurrence before the
  boundary (``is_pre_launch``). Occurrences are full dates, so an employee
  whose 2026 birthday is excluded is processed normally in 2027.
* The pre-launch backlog that already exists is cleared exactly once, by an
  explicit admin confirmation (``apply_clean_start``): orders are moved to
  CANCELLED with ``exception_reason=PRE_LAUNCH_EXCLUDED`` through the
  ordinary transition path. No supplier email is sent, nothing is deleted,
  and a cancelled order can still be reopened. ``clean_start_applied_at``
  makes the action single-use, so later settings changes never repeat it,
  and nothing re-cancels a deliberately reopened order.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import ActorType, ExceptionReason, OrderStatus
from app.models.birthday_order import BirthdayOrder
from app.models.detection_config import BirthdayDetectionConfig
from app.services import order_status_service

# Non-terminal states the clean start moves to CANCELLED — every state
# ALLOWED_TRANSITIONS lets reach CANCELLED. UNABLE_TO_FULFIL (no CANCELLED
# edge) and DELIVERED (auto-completes) are deliberately left alone.
CLEAN_START_STATUSES: tuple[str, ...] = (
    OrderStatus.PENDING_VERIFICATION.value,
    OrderStatus.REQUIRES_REVIEW.value,
    OrderStatus.REQUIRES_ATTENTION.value,
    OrderStatus.ON_HOLD.value,
    OrderStatus.SENT_TO_SUPPLIER.value,
    OrderStatus.CHANGE_REQUESTED.value,
    OrderStatus.CONFIRMED.value,
    OrderStatus.PREPARING.value,
    OrderStatus.OUT_FOR_DELIVERY.value,
)


class CleanStartError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def first_eligible_birthday(config: BirthdayDetectionConfig) -> date | None:
    if config.operational_start_date is None:
        return None
    return config.operational_start_date + timedelta(days=config.supplier_lead_time_days or 0)


def is_pre_launch(occurrence_date: date, config: BirthdayDetectionConfig) -> bool:
    boundary = first_eligible_birthday(config)
    return boundary is not None and occurrence_date < boundary


def _candidates(db: Session, boundary: date) -> list[BirthdayOrder]:
    stmt = (
        select(BirthdayOrder)
        .where(BirthdayOrder.birthday_date < boundary, BirthdayOrder.status.in_(CLEAN_START_STATUSES))
        .order_by(BirthdayOrder.birthday_date.asc(), BirthdayOrder.id.asc())
    )
    return list(db.execute(stmt).scalars().all())


def preview_clean_start(db: Session, config: BirthdayDetectionConfig) -> dict:
    boundary = first_eligible_birthday(config)
    orders = _candidates(db, boundary) if boundary is not None and config.clean_start_applied_at is None else []
    return {
        "operational_start_date": config.operational_start_date,
        "supplier_lead_time_days": config.supplier_lead_time_days,
        "first_eligible_birthday": boundary,
        "total": len(orders),
        "by_status": dict(Counter(o.status for o in orders)),
        "released_to_supplier": sum(1 for o in orders if o.released_at is not None),
        "already_applied": config.clean_start_applied_at is not None,
        "clean_start_applied_at": config.clean_start_applied_at,
        "clean_start_excluded_count": config.clean_start_excluded_count,
    }


def apply_clean_start(
    db: Session, config: BirthdayDetectionConfig, *, confirmed_first_eligible: date,
    actor_id: int | None, actor_display_name: str | None = None,
) -> int:
    if config.clean_start_applied_at is not None:
        raise CleanStartError(409, "The clean start has already been applied")
    boundary = first_eligible_birthday(config)
    if boundary is None:
        raise CleanStartError(422, "Set the operational start date before applying the clean start")
    if confirmed_first_eligible != boundary:
        raise CleanStartError(
            409, f"Settings changed since the preview: first eligible birthday is now {boundary.isoformat()}"
        )

    detail = f"Excluded — birthday before operational start (first eligible {boundary.isoformat()})"
    excluded = 0
    for order in _candidates(db, boundary):
        order_status_service.transition(
            db, order, OrderStatus.CANCELLED,
            actor_id=actor_id, actor_type=ActorType.USER, detail=detail,
            actor_display_name=actor_display_name,
        )
        order.exception_reason = ExceptionReason.PRE_LAUNCH_EXCLUDED.value
        excluded += 1

    config.clean_start_applied_at = datetime.now(UTC)
    config.clean_start_applied_by = actor_id
    config.clean_start_excluded_count = excluded
    config.clean_start_first_eligible = boundary
    db.commit()
    return excluded
