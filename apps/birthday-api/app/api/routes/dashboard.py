"""Phase C internal dashboard endpoints — BirthdayScope, permission-gated
(plan §6)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_birthday_permission
from app.api.routes.config import get_or_create_config
from app.core.constants import LeadTimeClass, OrderStatus
from app.db.session import get_db
from app.models.birthday_order import BirthdayOrder
from app.repositories.birthday_order_repository import BirthdayOrderRepository
from app.schemas.dashboard import DashboardSummary, UpcomingOrdersResponse
from app.schemas.order import BirthdayOrderSummary

router = APIRouter(prefix="/api/birthday", tags=["birthday-dashboard"])

EXCEPTION_STATUSES = {OrderStatus.REQUIRES_ATTENTION.value, OrderStatus.ON_HOLD.value}


@router.get("/dashboard", response_model=DashboardSummary)
def get_dashboard(
    db: Session = Depends(get_db),
    _scope=Depends(require_birthday_permission("birthday.dashboard.read")),
) -> DashboardSummary:
    total_orders = db.execute(select(func.count()).select_from(BirthdayOrder)).scalar_one()

    by_status: dict[str, int] = {s.value: 0 for s in OrderStatus}
    for status_value, count in db.execute(
        select(BirthdayOrder.status, func.count()).group_by(BirthdayOrder.status)
    ).all():
        by_status[status_value] = count

    by_lead_time_class: dict[str, int] = {c.value: 0 for c in LeadTimeClass}
    for class_value, count in db.execute(
        select(BirthdayOrder.lead_time_class, func.count()).group_by(BirthdayOrder.lead_time_class)
    ).all():
        by_lead_time_class[class_value] = count

    exceptions_count = sum(by_status.get(s, 0) for s in EXCEPTION_STATUSES)
    repo = BirthdayOrderRepository(db)
    upcoming_count = len(repo.list_upcoming(days_ahead=14))

    config = get_or_create_config(db)
    sla_cutoff = datetime.now(UTC) - timedelta(hours=config.acknowledgement_sla_hours)

    return DashboardSummary(
        total_orders=total_orders,
        by_status=by_status,
        by_lead_time_class=by_lead_time_class,
        upcoming_count=upcoming_count,
        exceptions_count=exceptions_count,
        pending_verification_count=repo.count_pending_verification(),
        verification_overdue_count=repo.count_verification_overdue(),
        requires_review_count=repo.count_requires_review(),
        supplier_not_accepted_count=repo.count_supplier_not_accepted(older_than=sla_cutoff),
        deliveries_today_at_risk_count=repo.count_deliveries_today_at_risk(),
    )


@router.get("/upcoming", response_model=UpcomingOrdersResponse)
def get_upcoming(
    days_ahead: int = 14,
    db: Session = Depends(get_db),
    _scope=Depends(require_birthday_permission("birthday.dashboard.read")),
) -> UpcomingOrdersResponse:
    orders = BirthdayOrderRepository(db).list_upcoming(days_ahead=days_ahead)
    return UpcomingOrdersResponse(
        days_ahead=days_ahead,
        orders=[BirthdayOrderSummary.model_validate(o) for o in orders],
    )
